variable "bedrock_model_id" {
  description = "Bedrock model or inference profile ID used for explanations"
  type        = string
  default     = "us.amazon.nova-2-lite-v1:0"
}

variable "bedrock_client" {
  description = "converse (any Bedrock text model), mantle (Claude, Messages API endpoint), invoke (Claude, InvokeModel), or disabled"
  type        = string
  default     = "converse"
  validation {
    condition     = contains(["converse", "mantle", "invoke", "disabled"], var.bedrock_client)
    error_message = "bedrock_client must be converse, mantle, invoke or disabled."
  }
}

variable "bedrock_daily_call_limit" {
  description = "Maximum Bedrock calls per UTC day (cache misses only)"
  type        = number
  default     = 100
}

variable "weekly_scenario_enabled" {
  description = "Run the partial demo scenario every Monday 03:00 UTC (off during judging to keep the verified demo fixed)"
  type        = bool
  default     = false
}
