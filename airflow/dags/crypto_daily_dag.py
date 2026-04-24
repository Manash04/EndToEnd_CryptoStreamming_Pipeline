"""
crypto_daily_dag.py
====================
Airflow DAG that runs every day at 3 PM UTC.
Spark is installed inside the Airflow container (via Dockerfile),
so spark-submit runs directly without needing docker exec.
"""

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
import psycopg2

default_args = {
    "owner":            "crypto-pipeline",
    "depends_on_past":  False,
    "retries":          1,
    "retry_delay":      timedelta(minutes=2),
    "email_on_failure": False,
}

ADLS_ACCOUNT   = os.getenv("ADLS_ACCOUNT_NAME", "")
ADLS_KEY       = os.getenv("ADLS_ACCOUNT_KEY",  "")
ADLS_CONTAINER = os.getenv("ADLS_CONTAINER",    "crypto-lake-new")
PG_HOST        = os.getenv("PG_HOST",           "postgres")
PG_DB          = os.getenv("PG_DB",             "crypto_analytics")
PG_USER        = os.getenv("PG_USER",           "crypto")
PG_PASS        = os.getenv("PG_PASS",           "crypto123")


def check_adls_data(**context):
    """
    Verify yesterday's Parquet data exists in ADLS before
    running the expensive Spark job.
    Checks BTCUSDT as proxy for all 4 symbols.
    """
    from azure.storage.filedatalake import DataLakeServiceClient

    execution_date = context.get("logical_date") or context.get("execution_date")
    yesterday = (execution_date - timedelta(days=1)).strftime("%Y-%m-%d")

    account_url = f"https://{ADLS_ACCOUNT}.dfs.core.windows.net"
    client = DataLakeServiceClient(account_url=account_url, credential=ADLS_KEY)
    fs = client.get_file_system_client(ADLS_CONTAINER)

    path = f"raw/trades/symbol=BTCUSDT/date_partition={yesterday}"

    try:
        paths = list(fs.get_paths(path=path, max_results=1))
        if not paths:
            raise ValueError(
                f"No data found in ADLS for {yesterday} at {path}. "
                "Make sure Spark streaming job was running."
            )
        print(f"ADLS check passed: data exists for {yesterday}")
    except Exception as e:
        if "PathNotFound" in str(e) or "ResourceNotFoundError" in str(e):
            raise ValueError(
                f"ADLS path not found: {path}. "
                f"Spark streaming job may not have run on {yesterday}."
            )
        raise


def log_dag_run(**context):
    """Write a success record to Postgres pipeline_metrics."""
    execution_date = context.get("logical_date") or context.get("execution_date")
    yesterday = (execution_date - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = psycopg2.connect(
        host=PG_HOST, dbname=PG_DB,
        user=PG_USER, password=PG_PASS
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pipeline_metrics
                    (recorded_at, topic, query_name, is_active, batch_id)
                VALUES (NOW(), 'AIRFLOW', %s, TRUE, 0)
            """, (f"daily_dag_success:{yesterday}",))
    conn.close()
    print(f"DAG run logged for {yesterday}")


with DAG(
    dag_id="crypto_daily_analysis",
    default_args=default_args,
    description="Daily batch analysis of crypto trade data from ADLS → Postgres",
    schedule_interval="0 15 * * *",
    start_date=days_ago(1),
    catchup=False,
    tags=["crypto", "batch", "spark"],
) as dag:

    # Task 1 — verify yesterday's data exists in ADLS
    check_data = PythonOperator(
        task_id="check_adls_data",
        python_callable=check_adls_data,
        provide_context=True,
    )

    # Task 2 — run spark-submit directly inside Airflow container
    # Spark is installed in the Airflow image via airflow/Dockerfile
    # {{ ds }} = execution date YYYY-MM-DD (Airflow built-in template)
    run_spark = BashOperator(
        task_id="run_spark_batch",
        bash_command="""
            set -e
            echo "Running daily analysis for {{ ds }}"

            /opt/spark/bin/spark-submit \
              --master local[*] \
              --packages "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-azure:3.3.4,com.azure:azure-storage-blob:12.25.1,org.postgresql:postgresql:42.6.0" \
              --conf "spark.sql.shuffle.partitions=4" \
              --conf "spark.driver.memory=2g" \
              --conf "spark.sql.files.maxPartitionBytes=134217728" \
              --conf "spark.hadoop.fs.azure.account.key.{{ params.adls_account }}.dfs.core.windows.net={{ params.adls_key }}" \
              /opt/airflow/batch/daily_analysis.py \
              --date "{{ ds }}"

            echo "Spark batch completed for {{ ds }}"
        """,
        params={
            "adls_account":   ADLS_ACCOUNT,
            "adls_key":       ADLS_KEY,
            "adls_container": ADLS_CONTAINER,
        },
        env={
            "ADLS_ACCOUNT_NAME": ADLS_ACCOUNT,
            "ADLS_ACCOUNT_KEY":  ADLS_KEY,
            "ADLS_CONTAINER":    ADLS_CONTAINER,
            "PG_HOST":           PG_HOST,
            "PG_DB":             PG_DB,
            "PG_USER":           PG_USER,
            "PG_PASS":           PG_PASS,
            "JAVA_HOME":         "/usr/lib/jvm/java-17-openjdk-amd64",
            "SPARK_HOME":        "/opt/spark",
            "PATH":              "/opt/spark/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )

    # Task 3 — log success to Postgres
    log_run = PythonOperator(
        task_id="log_dag_run",
        python_callable=log_dag_run,
        provide_context=True,
    )

    # Pipeline order: check data → run spark → log success
    check_data >> run_spark >> log_run