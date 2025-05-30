provider "aws" {
  region = var.aws_region
}

# S3 bucket for raw data
resource "aws_s3_bucket" "oakvale_raw_bucket" {
  bucket = var.raw_bucket_name
}

# S3 bucket for lakehouse
resource "aws_s3_bucket" "oakvale_lakehouse_bucket" {
  bucket = var.lakehouse_bucket_name
}

# Create folder structure in lakehouse bucket
resource "aws_s3_object" "bronze_folder" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  key    = "lakehouse/bronze/"
  content_type = "application/x-directory"
}

resource "aws_s3_object" "silver_folder" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  key    = "lakehouse/silver/"
  content_type = "application/x-directory"
}

resource "aws_s3_object" "gold_folder" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  key    = "lakehouse/gold/"
  content_type = "application/x-directory"
}

# Upload delta jar files to lakehouse bucket
resource "aws_s3_object" "delta_jar_core" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  key    = "delta_jar/delta-core_2.12-2.1.0.jar"
  source = "../delta_jar/delta-core_2.12-2.1.0.jar"
}

resource "aws_s3_object" "delta_jar_storage" {
  bucket = aws_s3_bucket.oakvale_lakehouse_bucket.id
  key    = "delta_jar/delta-storage-2.1.0.jar"
  source = "../delta_jar/delta-storage-2.1.0.jar"
}

# S3 bucket for Glue scripts
resource "aws_s3_bucket" "oakvale_lakehouse_glue_bucket" {
  bucket = var.glue_script_bucket
}

# Glue databases for the lakehouse
resource "aws_glue_catalog_database" "bronze_database" {
  name = var.bronze_glue_database
  location_uri = var.s3_location_bronze_glue_database
}

resource "aws_glue_catalog_database" "silver_database" {
  name = var.silver_glue_database
  location_uri = var.s3_location_silver_glue_database
}

resource "aws_glue_catalog_database" "gold_database" {
  name = var.gold_glue_database
  location_uri = var.s3_location_gold_glue_database
}

# Glue IAM role 
resource "aws_iam_role" "glue_iam_role" {
  name = var.glue_iam_role_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      },
    ]
  })

  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
  ]
}

# Lambda function for data generation
resource "aws_lambda_function" "movie_data_generator" {
  function_name = "oakvale-movie-data-generator"
  handler       = "api_data.lambda_handler"
  runtime       = "python3.9"
  role          = aws_iam_role.lambda_execution_role.arn
  timeout       = 300
  memory_size   = 256
  
  # Assuming the code is packaged as a zip file
  filename      = "../lambda_package.zip"
  
  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.oakvale_raw_bucket.bucket
      NUM_MOVIES  = "100"
    }
  }
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_execution_role" {
  name = "oakvale-lambda-execution-role"
  
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

# Attach policies to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

# CloudWatch Event Rule to trigger Lambda function daily
resource "aws_cloudwatch_event_rule" "daily_lambda_trigger" {
  name                = "daily-movie-data-generator"
  description         = "Triggers the movie data generator Lambda function daily"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.daily_lambda_trigger.name
  target_id = "movie_data_generator"
  arn       = aws_lambda_function.movie_data_generator.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.movie_data_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_lambda_trigger.arn
} 