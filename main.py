import os
from datetime import datetime, timezone

import requests
import sqlalchemy
from flask import Flask, jsonify
from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import text


app = Flask(__name__)

connector = None
db_engine = None


def get_db_engine():
    global connector
    global db_engine

    if db_engine is not None:
        return db_engine

    # Values configured in Cloud Run Environment Variables
    instance_connection_name = os.environ["INSTANCE_CONNECTION_NAME"]
    db_user = os.environ["DB_USER"]
    db_password = os.environ["DB_PASS"]
    db_name = os.environ["DB_NAME"]

    # Initial POC uses Cloud SQL public IP through the connector
    connector = Connector(
        ip_type=IPTypes.PUBLIC,
        refresh_strategy="LAZY"
    )

    def get_connection():
        return connector.connect(
            instance_connection_name,
            "pytds",
            user=db_user,
            password=db_password,
            db=db_name
        )

    db_engine = sqlalchemy.create_engine(
        "mssql+pytds://",
        creator=get_connection,
        pool_pre_ping=True
    )

    return db_engine


@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "success",
        "message": "Cloud Run Python service is running"
    }), 200


@app.route("/load-users", methods=["GET", "POST"])
def load_users():

    api_url = "https://jsonplaceholder.typicode.com/users"

    try:
        # ----------------------------
        # Step 1 - Call sample API
        # ----------------------------
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        users = response.json()

        print(f"Received {len(users)} users from API")

        # ----------------------------
        # Step 2 - Connect to Cloud SQL
        # ----------------------------
        engine = get_db_engine()

        # ----------------------------
        # Step 3 - Insert/update records
        # ----------------------------
        merge_sql = text("""
            MERGE ApiUsers AS target

            USING (
                SELECT
                    :id AS Id,
                    :name AS Name,
                    :username AS Username,
                    :email AS Email,
                    :phone AS Phone,
                    :website AS Website,
                    :loaded_at AS LoadedAt
            ) AS source

            ON target.Id = source.Id

            WHEN MATCHED THEN
                UPDATE SET
                    Name = source.Name,
                    Username = source.Username,
                    Email = source.Email,
                    Phone = source.Phone,
                    Website = source.Website,
                    LoadedAt = source.LoadedAt

            WHEN NOT MATCHED THEN
                INSERT (
                    Id,
                    Name,
                    Username,
                    Email,
                    Phone,
                    Website,
                    LoadedAt
                )
                VALUES (
                    source.Id,
                    source.Name,
                    source.Username,
                    source.Email,
                    source.Phone,
                    source.Website,
                    source.LoadedAt
                );
        """)

        processed_count = 0

        with engine.begin() as connection:

            for user in users:

                connection.execute(
                    merge_sql,
                    {
                        "id": user.get("id"),
                        "name": user.get("name"),
                        "username": user.get("username"),
                        "email": user.get("email"),
                        "phone": user.get("phone"),
                        "website": user.get("website"),
                        "loaded_at": datetime.now(timezone.utc).replace(
                            tzinfo=None
                        )
                    }
                )

                processed_count += 1

        print(f"Successfully processed {processed_count} records")

        return jsonify({
            "status": "success",
            "records_received": len(users),
            "records_processed": processed_count,
            "destination_database": os.environ["DB_NAME"],
            "destination_table": "ApiUsers"
        }), 200

    except requests.RequestException as api_error:

        print(f"API error: {str(api_error)}")

        return jsonify({
            "status": "failed",
            "stage": "API",
            "error": str(api_error)
        }), 500

    except Exception as sql_error:

        print(f"SQL error: {str(sql_error)}")

        return jsonify({
            "status": "failed",
            "stage": "Cloud SQL",
            "error": str(sql_error)
        }), 500


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )