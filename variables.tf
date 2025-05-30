variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "raw_bucket_name" {
  description = "Name of the S3 bucket for storing raw data from Lambda"
  type        = string
  default     = "oakvale-raw-data"
}

variable "lakehouse_bucket_name" {
  description = "Name of the S3 bucket for the Lakehouse"
  type        = string
  default     = "oakvale-lakehouse"
}

variable "glue_script_bucket" {
  description = "Name of the S3 bucket for storing Glue scripts"
  type        = string
  default     = "oakvale-glue-scripts"
}

variable "bronze_glue_database" {
  description = "Name of the bronze Glue database"
  type        = string
  default     = "oakvale_bronze"
}

variable "silver_glue_database" {
  description = "Name of the silver Glue database"
  type        = string
  default     = "oakvale_silver"
}

variable "gold_glue_database" {
  description = "Name of the gold Glue database"
  type        = string
  default     = "oakvale_gold"
}

variable "s3_location_bronze_glue_database" {
  description = "S3 location URI for the bronze Glue database"
  type        = string
  default     = "s3://oakvale-lakehouse/lakehouse/bronze/"
}

variable "s3_location_silver_glue_database" {
  description = "S3 location URI for the silver Glue database"
  type        = string
  default     = "s3://oakvale-lakehouse/lakehouse/silver/"
}

variable "s3_location_gold_glue_database" {
  description = "S3 location URI for the gold Glue database"
  type        = string
  default     = "s3://oakvale-lakehouse/lakehouse/gold/"
}

variable "glue_iam_role_name" {
  description = "Name of the IAM role for Glue jobs"
  type        = string
  default     = "oakvale-glue-service-role"
} 