"""
crypto_daily_dag.py
====================
Airflow DAG that runs every day at 3 PM UTC and triggers the
PySpark batch job inside the spark-master container via DockerOperator.
"""

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount
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

# Absolute path to your spark folder on the Windows host
# This is mounted into the Docker container so spark-submit can find daily_analysis.py
SPARK_APPS_HOST_PATH = "/c/Users/MManashBandhuBarik/Documents/Project/spark"


def check_adls_data(**context):
    """
    Verify yesterday's Parquet data exists in ADLS before
    running the expensive Spark job. Checks BTCUSDT as proxy
    for all 4 symbols.
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
                "Pipeline may not have been running."
            )
        print(f"ADLS check passed: data exists for {yesterday}")
    except Exception as e:
        if "PathNotFound" in str(e) or "ResourceNotFoundError" in str(e):
            raise ValueError(
                f"ADLS path not found: {path}. "
                f"Make sure Spark streaming job was running on {yesterday}."
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
                VALUES
                    (NOW(), 'AIRFLOW', %s, TRUE, 0)
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

    # Task 1 — verify data exists in ADLS
    check_data = PythonOperator(
        task_id="check_adls_data",
        python_callable=check_adls_data,
        provide_context=True,
    )

    # Task 2 — run spark-submit inside a fresh apache/spark container
    # DockerOperator spins up a container, runs the job, then removes it
    # {{ ds }} is Airflow's built-in date template = execution date (YYYY-MM-DD)
    run_spark = DockerOperator(
    task_id="run_spark_batch",
    image="apache/spark:3.5.0",
    container_name="airflow_spark_batch",
    api_version="auto",
    auto_remove=True,
    docker_url="unix:///var/run/docker.sock",
    network_mode="project_default",
    user="root",                    # ← run as root inside container
    mounts=[
        Mount(
            source=SPARK_APPS_HOST_PATH,
            target="/opt/spark-apps",
            type="bind",
        ),
        Mount(
            source="spark-ivy-cache",  # ← named volume for JAR cache
            target="/root/.ivy2",
            type="volume",
        ),
    ],
    environment={...},
    command=(
        "/opt/spark/bin/spark-submit "
        "--master local[*] "
        "--conf spark.jars.ivy=/root/.ivy2 "   # ← tell Spark to use root's ivy dir
        "--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
        "org.apache.hadoop:hadoop-azure:3.3.4,"
        "com.azure:azure-storage-blob:12.25.1,"
        "org.postgresql:postgresql:42.6.0 "
        "--conf spark.sql.shuffle.partitions=4 "
        "--conf spark.driver.memory=2g "
        "--conf spark.sql.files.maxPartitionBytes=134217728 "
        f"--conf spark.hadoop.fs.azure.account.key.{ADLS_ACCOUNT}.dfs.core.windows.net={ADLS_KEY} "
        "/opt/spark-apps/daily_analysis.py "
        "--date {{ ds }}"
    ),
    mount_tmp_dir=False,
)

    # Task 3 — log success to Postgres
    log_run = PythonOperator(
        task_id="log_dag_run",
        python_callable=log_dag_run,
        provide_context=True,
    )

    check_data >> run_spark >> log_run