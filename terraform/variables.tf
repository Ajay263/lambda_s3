variable "bucket_name" {
  type        = string
  description = "S3 bucket name for storing API data"
  default     = "movie-api-data-daily"
}

variable "lambda_ecr_repo" {
  type        = string
  description = "ECR repository name for Lambda container"
  default     = "ecr-repo-lambda"
}

variable "eventbridge_rule" {
  type        = string
  description = "EventBridge rule name"
  default     = "run_daily"
}

variable "lambda_iam_role_name" {
  type        = string
  description = "IAM role name for Lambda function"
  default     = "s3_cloudwatch_ecr_lambdarole"
}

variable "lambda_function_name" {
  type        = string
  description = "Lambda function name"
  default     = "movie-api-extractor"
}

variable "region" {
  type        = string
  description = "AWS region"
  default     = "eu-west-3"
}