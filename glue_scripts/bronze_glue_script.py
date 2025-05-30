import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import DataFrame
import logging

args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)

spark = (
    glueContext.sparkSession.builder.config(
        "spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension"
    )
    .config(
        "spark.sql.catalog.spark_catalog",
        "org.apache.spark.sql.delta.catalog.DeltaCatalog",
    )
    .getOrCreate()
)

job = Job(glueContext)
job.init(args['JOB_NAME'], args)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def read_raw_data(path: str) -> DataFrame:
    """
    Read data from s3

    :param path : path to the file stored in S3

    :return spark dataframe
    """
    df = spark.read.option("multiline", "true").json(path)
    return df


def write_delta_tables(table: str, database: str, df: DataFrame):
    """
    Write to delta lake on S3 and glue catalog

    :param table : delta table name (will be use in Glue datacatalog)
    :param database : glue database name
    :param df : spark dataframe
    """
    df.write.format("delta").mode("overwrite").saveAsTable(f"{database}.{table}")
    logger.info(f"Table {table} successfully loaded to {database} database!!")


def main():
    # Path to raw movie data in S3
    movies_path = "s3://oakvale-raw-data/Movies/*/*.json"
    
    # Read raw data
    movies_df = read_raw_data(movies_path)
    
    # Define table name and database
    movies_table = "movies_info"
    database = "oakvale_bronze"
    
    # Write to delta table
    write_delta_tables(movies_table, database, movies_df)


if __name__ == '__main__':
    main()
    job.commit() 