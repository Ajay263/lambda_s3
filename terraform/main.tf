terraform {
  required_version = ">= 1.9.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket       = "gamepulse-tf-backend-resources"
    key          = "terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
provider "aws" {
  region = var.region
}

# Additional provider for us-east-1 region
provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"
}

locals {
  lambda_image_exists = var.lambda_image_exists
}

# S3 Buckets for Oakvale data lakehouse
resource "aws_s3_bucket" "oakvale_raw_bucket" {
  provider = aws.us-east-1
  bucket   = var.raw_bucket_name
}

resource "aws_s3_bucket" "oakvale_lakehouse_bucket" {
  provider = aws.us-east-1
  bucket   = var.lakehouse_bucket_name
}

resource "aws_s3_bucket" "oakvale_lakehouse_glue_bucket" {
  provider = aws.us-east-1
  bucket   = var.glue_bucket_name
}

resource "aws_s3_bucket_versioning" "oakvale_raw_bucket_versioning" {
  bucket = aws_s3_bucket.oakvale_raw_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "oakvale_lakehouse_bucket_versioning" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "oakvale_lakehouse_glue_bucket_versioning" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ECR Repository
resource "aws_ecr_repository" "ecr_repo" {
  name         = var.lambda_ecr_repo
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  lifecycle {
    ignore_changes        = [name]
    create_before_destroy = true
  }
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_iam_role" {
  name = var.lambda_iam_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  lifecycle {
    ignore_changes        = [name]
    create_before_destroy = true
  }
}

# IAM Role for Glue
resource "aws_iam_role" "glue_iam_role" {
  name = "oakvale_glue_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for Glue
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_iam_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3_policy" {
  name = "glue_s3_access"
  role = aws_iam_role.glue_iam_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.oakvale_raw_bucket.arn}/*",
          "${aws_s3_bucket.oakvale_lakehouse_bucket.arn}/*",
          "${aws_s3_bucket.oakvale_lakehouse_glue_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.oakvale_raw_bucket.arn,
          aws_s3_bucket.oakvale_lakehouse_bucket.arn,
          aws_s3_bucket.oakvale_lakehouse_glue_bucket.arn
        ]
      }
    ]
  })
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "lambda_policy" {
  name = "lambda_execution_policy"
  role = aws_iam_role.lambda_iam_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.oakvale_raw_bucket.arn}/*",
          "${aws_s3_bucket.oakvale_lakehouse_bucket.arn}/*",
          "${aws_s3_bucket.oakvale_lakehouse_glue_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.oakvale_raw_bucket.arn,
          aws_s3_bucket.oakvale_lakehouse_bucket.arn,
          aws_s3_bucket.oakvale_lakehouse_glue_bucket.arn
        ]
      }
    ]
  })
}

# Lambda Function - Only created when image exists
resource "aws_lambda_function" "movie_api_lambda" {
  count         = local.lambda_image_exists ? 1 : 0
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_iam_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.ecr_repo.repository_url}:latest"

  timeout = 60

  environment {
    variables = {
      RAW_BUCKET_NAME       = aws_s3_bucket.oakvale_raw_bucket.id
      LAKEHOUSE_BUCKET_NAME = aws_s3_bucket.oakvale_lakehouse_bucket.id
    }
  }

  depends_on = [aws_ecr_repository.ecr_repo]
}

# EventBridge Rule - Only created when Lambda exists
resource "aws_cloudwatch_event_rule" "event_rule" {
  count               = local.lambda_image_exists ? 1 : 0
  name                = var.eventbridge_rule
  description         = "Trigger Lambda daily"
  schedule_expression = "rate(1 day)"
}

# EventBridge Target - Only created when Lambda exists
resource "aws_cloudwatch_event_target" "lambda_target" {
  count     = local.lambda_image_exists ? 1 : 0
  rule      = aws_cloudwatch_event_rule.event_rule[0].name
  target_id = "TriggerLambdaTarget"
  arn       = aws_lambda_function.movie_api_lambda[0].arn
}

# Lambda Permission for EventBridge - Only created when Lambda exists
resource "aws_lambda_permission" "allow_eventbridge" {
  count         = local.lambda_image_exists ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.movie_api_lambda[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.event_rule[0].arn
}

# Upload Glue scripts to S3
resource "aws_s3_object" "bronze_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/bronze_glue_script.py"
  source = "../glue_scripts/bronze_glue_script.py"
}

resource "aws_s3_object" "silver_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/silver_glue_script.py"
  source = "../glue_scripts/silver_glue_script.py"
}

resource "aws_s3_object" "gold_script" {
  bucket = aws_s3_bucket.oakvale_lakehouse_glue_bucket.id
  key    = "scripts/gold_glue_script.py"
  source = "../glue_scripts/gold_glue_script.py"
}

# Define local variables for job configuration
locals {
  jobs = {
    bronze = {
      name        = "bronze"
      script_name = "bronze_glue_script"
    },
    silver = {
      name        = "silver"
      script_name = "silver_glue_script"
    },
    gold = {
      name        = "gold"
      script_name = "gold_glue_script"
    }
  }
}

# Glue ETL Jobs using for_each
resource "aws_glue_job" "etl_jobs" {
  for_each = local.jobs

  name              = "oakvale-${each.value.name}-job"
  role_arn          = aws_iam_role.glue_iam_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60
  max_retries       = 0

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.oakvale_lakehouse_glue_bucket.bucket}/scripts/${each.value.script_name}.py"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/temp/"
    "--extra-jars"                       = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-core_2.12-2.1.0.jar,s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/delta_jar/delta-storage-2.1.0.jar"
    "--conf"                             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
    "--class"                            = "GlueApp"
    "--enable-auto-scaling"              = "true"
    "--source-path"                      = "s3://${aws_s3_bucket.oakvale_raw_bucket.bucket}/"
    "--destination-path"                 = "s3://${aws_s3_bucket.oakvale_lakehouse_bucket.bucket}/lakehouse/${each.value.name}/"
    "--job-name"                         = "oakvale-${each.value.name}-job"
  }

  execution_property {
    max_concurrent_runs = 1
  }

  tags = {
    Environment = "production"
    Service     = "glue"
    Project     = "Oakvale"
  }
}

# Glue workflow to orchestrate the jobs
resource "aws_glue_workflow" "lakehouse_workflow" {
  name = "oakvale-lakehouse-workflow"

  tags = {
    Environment = "production"
    Service     = "glue"
    Project     = "Oakvale"
  }
}

# Trigger for bronze job
resource "aws_glue_trigger" "bronze_trigger" {
  name          = "oakvale-bronze-trigger"
  type          = "SCHEDULED"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name

  schedule = "cron(0 1 * * ? *)" # Run at 1:00 AM UTC every day

  actions {
    job_name = aws_glue_job.etl_jobs["bronze"].name
  }
}

# Trigger for silver job (runs after bronze job)
resource "aws_glue_trigger" "silver_trigger" {
  name          = "oakvale-silver-trigger"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name

  predicate {
    conditions {
      job_name = aws_glue_job.etl_jobs["bronze"].name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.etl_jobs["silver"].name
  }
}

# Trigger for gold job (runs after silver job)
resource "aws_glue_trigger" "gold_trigger" {
  name          = "oakvale-gold-trigger"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.lakehouse_workflow.name

  predicate {
    conditions {
      job_name = aws_glue_job.etl_jobs["silver"].name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = aws_glue_job.etl_jobs["gold"].name
  }
}

# S3 Bucket for weather data
resource "aws_s3_bucket" "weather_data_bucket" {
  provider = aws.us-east-1
  bucket   = "${var.raw_bucket_name}-weather"
}

resource "aws_s3_bucket_versioning" "weather_data_bucket_versioning" {
  bucket = aws_s3_bucket.weather_data_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Lambda IAM Role for Weather Data Collection
resource "aws_iam_role" "weather_lambda_role" {
  name = "weather_data_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for Weather Lambda
resource "aws_iam_role_policy" "weather_lambda_policy" {
  name = "weather_lambda_policy"
  role = aws_iam_role.weather_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "${aws_s3_bucket.weather_data_bucket.arn}",
          "${aws_s3_bucket.weather_data_bucket.arn}/*"
        ]
      }
    ]
  })
}

# ECR Repositories for Weather Collectors
resource "aws_ecr_repository" "weather_historical_ecr" {
  name         = "weather-historical-collector"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "weather_hourly_ecr" {
  name         = "weather-hourly-collector"
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Historical Weather Lambda Function (Container)
resource "aws_lambda_function" "historical_weather_lambda" {
  function_name = "historical_weather_collector"
  role          = aws_iam_role.weather_lambda_role.arn
  timeout       = 300
  memory_size   = 256

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.weather_historical_ecr.repository_url}:latest"

  environment {
    variables = {
      WEATHER_BUCKET = aws_s3_bucket.weather_data_bucket.id
    }
  }

  depends_on = [
    aws_ecr_repository.weather_historical_ecr,
    aws_iam_role_policy.weather_lambda_policy
  ]
}

# Hourly Weather Lambda Function (Container)
resource "aws_lambda_function" "hourly_weather_lambda" {
  function_name = "hourly_weather_collector"
  role          = aws_iam_role.weather_lambda_role.arn
  timeout       = 60
  memory_size   = 128

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.weather_hourly_ecr.repository_url}:latest"

  environment {
    variables = {
      WEATHER_BUCKET = aws_s3_bucket.weather_data_bucket.id
    }
  }

  depends_on = [
    aws_ecr_repository.weather_hourly_ecr,
    aws_iam_role_policy.weather_lambda_policy
  ]

  # Force update when image changes
  lifecycle {
    replace_triggered_by = [
      aws_ecr_repository.weather_hourly_ecr
    ]
  }

  # Add a timestamp to force updates
  source_code_hash = timestamp()
}

# EventBridge Rule for Hourly Updates
resource "aws_cloudwatch_event_rule" "hourly_weather_rule" {
  name                = "hourly-weather-collection"
  description         = "Trigger weather data collection every hour"
  schedule_expression = "rate(1 hour)"
}

resource "aws_cloudwatch_event_target" "hourly_weather_target" {
  rule      = aws_cloudwatch_event_rule.hourly_weather_rule.name
  target_id = "WeatherLambdaTarget"
  arn       = aws_lambda_function.hourly_weather_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge_hourly" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hourly_weather_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.hourly_weather_rule.arn
}