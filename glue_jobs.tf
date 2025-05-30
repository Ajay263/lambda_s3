# Upload Glue scripts to S3
resource "aws_s3_object" "bronze_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/bronze_glue_script.py"
  source = "glue_scripts/bronze_glue_script.py"
}

resource "aws_s3_object" "silver_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/silver_glue_script.py"
  source = "glue_scripts/silver_glue_script.py"
}

resource "aws_s3_object" "gold_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/gold_glue_script.py"
  source = "glue_scripts/gold_glue_script.py"
}

# Glue job for bronze layer
resource "aws_glue_job" "bronze_job" {
  name     = "oakvale-bronze-job"
  role_arn = aws_iam_role.glue_iam_role.arn
  
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.oakvale_lakehouse_glue_bucket.bucket}/scripts/bronze_glue_script.py"
    python_version  = "3"
  }
  
  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/temp/"
    "--extra-jars"                       = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-core_2.12-2.1.0.jar,s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-storage-2.1.0.jar"
    "--conf"                             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
    "--class"                            = "GlueApp"
  }
  
  max_retries      = 0
  timeout          = 60
  worker_type      = "G.1X"
  number_of_workers = 2
  
  execution_property {
    max_concurrent_runs = 1
  }
}

# Glue job for silver layer
resource "aws_glue_job" "silver_job" {
  name     = "oakvale-silver-job"
  role_arn = aws_iam_role.glue_iam_role.arn
  
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.oakvale_lakehouse_glue_bucket.bucket}/scripts/silver_glue_script.py"
    python_version  = "3"
  }
  
  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/temp/"
    "--extra-jars"                       = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-core_2.12-2.1.0.jar,s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-storage-2.1.0.jar"
    "--conf"                             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
    "--class"                            = "GlueApp"
  }
  
  max_retries      = 0
  timeout          = 60
  worker_type      = "G.1X"
  number_of_workers = 2
  
  execution_property {
    max_concurrent_runs = 1
  }
}

# Glue job for gold layer
resource "aws_glue_job" "gold_job" {
  name     = "oakvale-gold-job"
  role_arn = aws_iam_role.glue_iam_role.arn
  
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.oakvale_lakehouse_glue_bucket.bucket}/scripts/gold_glue_script.py"
    python_version  = "3"
  }
  
  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/temp/"
    "--extra-jars"                       = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-core_2.12-2.1.0.jar,s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-storage-2.1.0.jar"
    "--conf"                             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
    "--class"                            = "GlueApp"
  }
  
  max_retries      = 0
  timeout          = 60
  worker_type      = "G.1X"
  number_of_workers = 2
  
  execution_property {
    max_concurrent_runs = 1
  }
}

# Glue workflow to orchestrate the jobs
resource "aws_glue_workflow" "lakehouse_workflow" {
  name = "oakvale-lakehouse-workflow"
}

# Trigger for bronze job
resource "aws_glue_trigger" "bronze_trigger" {
  name          = "oakvale-bronze-trigger"
  type          = "SCHEDULED"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name
  
  schedule = "cron(0 1 * * ? *)"  # Run at 1:00 AM UTC every day
  
  actions {
    job_name = aws_glue_job.bronze_job.name
  }
}

# Trigger for silver job (runs after bronze job)
resource "aws_glue_trigger" "silver_trigger" {
  name          = "oakvale-silver-trigger"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name
  
  predicate {
    conditions {
      job_name = aws_glue_job.bronze_job.name
      state    = "SUCCEEDED"
    }
  }
  
  actions {
    job_name = aws_glue_job.silver_job.name
  }
}

# Trigger for gold job (runs after silver job)
resource "aws_glue_trigger" "gold_trigger" {
  name          = "oakvale-gold-trigger"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name
  
  predicate {
    conditions {
      job_name = aws_glue_job.silver_job.name
      state    = "SUCCEEDED"
    }
  }
  
  actions {
    job_name = aws_glue_job.gold_job.name
  }
} 