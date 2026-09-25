output "app_url" {
  value = "https://${aws_cloudfront_distribution.web.domain_name}"
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.api.api_endpoint
}

output "table_name" {
  value = aws_dynamodb_table.incidents.name
}

output "scenario_function" {
  value = aws_lambda_function.demo_scenario.function_name
}
