import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
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


def read_delta_table(table: str, database: str) -> DataFrame:
    """
    Read delta table stored in s3

    :param table : the table name
    :param database : the database name
    """
    df = spark.read.format('delta').load(
        f"s3://oakvale-lakehouse/lakehouse/{database}/{table}"
    )
    logger.info(f"Table {database}.{table} successfully loaded from delta lake!!")
    return df


def clean_movies_table(movies_df: DataFrame) -> DataFrame:
    """
    Clean movies info table: normalize rating, fix data types

    :param movies_df : movies spark dataframe

    :return spark dataframe
    """
    # Drop duplicates
    movies_df = movies_df.dropDuplicates(['id'])
    
    # Normalize rating column
    movies_df = movies_df.withColumn(
        "rating_category",
        F.when(F.col("rating") == "G", "General")
        .when(F.col("rating") == "PG", "Parental Guidance")
        .when(F.col("rating") == "PG-13", "Parents Strongly Cautioned")
        .when(F.col("rating") == "R", "Restricted")
        .when(F.col("rating") == "NC-17", "Adults Only")
        .otherwise("Not Rated"),
    )
    
    # Convert release_date to date type
    movies_df = movies_df.withColumn(
        'release_date', 
        F.to_date(F.col('release_date'))
    )
    
    # Add release_year column
    movies_df = movies_df.withColumn(
        'release_year',
        F.year(F.col('release_date'))
    )
    
    return movies_df


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
    # Define table names and databases
    movies_table = 'movies_info'
    
    bronze_database = 'oakvale_bronze'
    silver_database = 'oakvale_silver'
    
    # Read from bronze layer
    movies_df = read_delta_table(movies_table, bronze_database)
    
    # Clean data
    movies_clean_df = clean_movies_table(movies_df)
    
    # Write to silver layer
    write_delta_tables(movies_table, silver_database, movies_clean_df)


if __name__ == '__main__':
    main()
    job.commit() 