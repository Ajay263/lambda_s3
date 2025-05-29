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

# S3 Bucket for storing API data
resource "aws_s3_bucket" "movie_bucket" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "movie_bucket_versioning" {
  bucket = aws_s3_bucket.movie_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ECR Repository
resource "aws_ecr_repository" "ecr_repo" {
  name = var.lambda_ecr_repo

  image_scanning_configuration {
    scan_on_push = true
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
        Resource = "${aws_s3_bucket.movie_bucket.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.movie_bucket.arn
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "movie_api_lambda" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_iam_role.arn

  package_type = "Image"
  image_uri    = "${aws_ecr_repository.ecr_repo.repository_url}:latest"

  timeout = 60

  environment {
    variables = {
      BUCKET_NAME = aws_s3_bucket.movie_bucket.id
    }
  }

  depends_on = [aws_ecr_repository.ecr_repo]
}

# EventBridge Rule
resource "aws_cloudwatch_event_rule" "event_rule" {
  name                = var.eventbridge_rule
  description         = "Trigger Lambda daily"
  schedule_expression = "rate(1 day)"
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.event_rule.name
  target_id = "TriggerLambdaTarget"
  arn       = aws_lambda_function.movie_api_lambda.arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.movie_api_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.event_rule.arn
}
