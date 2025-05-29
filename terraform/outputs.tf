output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.movie_api_lambda.function_name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.ecr_repo.repository_url
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.movie_bucket.id
}