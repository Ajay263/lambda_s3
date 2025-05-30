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


def genre_metrics(movies_df: DataFrame) -> DataFrame:
    """
    Calculate metrics by genre: avg budget, avg box office, count

    :param movies_df : movies spark dataframe

    :return spark dataframe
    """
    genre_metrics_df = movies_df.groupBy('genre').agg(
        F.count('id').alias('movie_count'),
        F.round(F.avg('budget'), 2).alias('avg_budget'),
        F.round(F.avg('box_office'), 2).alias('avg_box_office'),
        F.round(F.avg('vote_average'), 2).alias('avg_rating')
    )
    
    return genre_metrics_df


def studio_metrics(movies_df: DataFrame) -> DataFrame:
    """
    Calculate metrics by studio: movie count, avg budget, avg box office

    :param movies_df : movies spark dataframe

    :return spark dataframe
    """
    studio_metrics_df = movies_df.groupBy('studio').agg(
        F.count('id').alias('movie_count'),
        F.round(F.avg('budget'), 2).alias('avg_budget'),
        F.round(F.avg('box_office'), 2).alias('avg_box_office'),
        F.round(F.sum('box_office'), 2).alias('total_box_office')
    ).orderBy(F.col('total_box_office').desc())
    
    return studio_metrics_df


def year_metrics(movies_df: DataFrame) -> DataFrame:
    """
    Calculate metrics by release year: movie count, avg budget, avg box office

    :param movies_df : movies spark dataframe

    :return spark dataframe
    """
    year_metrics_df = movies_df.groupBy('release_year').agg(
        F.count('id').alias('movie_count'),
        F.round(F.avg('budget'), 2).alias('avg_budget'),
        F.round(F.avg('box_office'), 2).alias('avg_box_office'),
        F.round(F.avg('vote_average'), 2).alias('avg_rating')
    ).orderBy('release_year')
    
    return year_metrics_df


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
    
    silver_database = 'oakvale_silver'
    gold_database = 'oakvale_gold'
    
    # Read from silver layer
    movies_df = read_delta_table(movies_table, silver_database)
    
    # Generate metrics
    genre_metrics_df = genre_metrics(movies_df)
    studio_metrics_df = studio_metrics(movies_df)
    year_metrics_df = year_metrics(movies_df)
    
    # Write to gold layer
    write_delta_tables("genre_metrics", gold_database, genre_metrics_df)
    write_delta_tables("studio_metrics", gold_database, studio_metrics_df)
    write_delta_tables("year_metrics", gold_database, year_metrics_df)


if __name__ == '__main__':
    main()
    job.commit() 