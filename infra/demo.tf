# Demo workload for controlled incidents. Only these resources are ever analyzed.

# -------------------------------------------------------------- orders API (the monitored workload)

resource "aws_iam_role" "demo_orders_api" {
  name = "${local.prefix}-demo-orders-api-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_cloudwatch_log_group" "demo_orders_api" {
  name              = "/aws/lambda/${local.demo_fn}"
  retention_in_days = 3
}

resource "aws_iam_role_policy" "demo_orders_api" {
  name = "${local.prefix}-demo-orders-api-logs"
  role = aws_iam_role.demo_orders_api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.demo_orders_api.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "demo_orders_api" {
  function_name    = local.demo_fn
  role             = aws_iam_role.demo_orders_api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "orders_api.handler"
  filename         = "${local.build_dir}/demo_orders_api.zip"
  source_code_hash = filebase64sha256("${local.build_dir}/demo_orders_api.zip")
  memory_size      = 128
  timeout          = 5
  environment {
    variables = {
      DOWNSTREAM_TIMEOUT_MS = "3000"
      MAX_RETRIES           = "0"
      RELEASE_VERSION       = "v2.13"
      RELEASE_APPLIED_AT    = "0"
    }
  }
  # The scenario generator changes the configuration at runtime; those changes are the
  # CloudTrail evidence and must not be reverted by Terraform.
  lifecycle {
    ignore_changes = [environment]
  }
  depends_on = [aws_cloudwatch_log_group.demo_orders_api]
}

resource "aws_lambda_function_event_invoke_config" "demo_orders_api" {
  function_name          = aws_lambda_function.demo_orders_api.function_name
  maximum_retry_attempts = 0
}

# -------------------------------------------------------------- alarms on the demo workload

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = local.alarm_names.latency
  alarm_description   = "Demo: average orders-api duration above 1,000 ms"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = local.demo_fn }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = local.alarm_names.errors
  alarm_description   = "Demo: orders-api errors above 10 per minute"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = local.demo_fn }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name          = local.alarm_names.throttles
  alarm_description   = "Demo: orders-api throttles above 20 per minute"
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = local.demo_fn }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

# -------------------------------------------------------------- scenario generator (not public)

resource "aws_iam_role" "demo_scenario" {
  name = "${local.prefix}-demo-scenario-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_cloudwatch_log_group" "demo_scenario" {
  name              = "/aws/lambda/${local.scenario_fn}"
  retention_in_days = 14
}

resource "aws_iam_role_policy" "demo_scenario" {
  name = "${local.prefix}-demo-scenario-policy"
  role = aws_iam_role.demo_scenario.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.demo_scenario.arn}:*"
      },
      {
        Sid    = "DemoWorkloadOnly"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:UpdateFunctionConfiguration"]
        Resource = [
          aws_lambda_function.demo_orders_api.arn,
          "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.scenario_fn}",
        ]
      },
    ]
  })
}

resource "aws_lambda_function" "demo_scenario" {
  function_name    = local.scenario_fn
  role             = aws_iam_role.demo_scenario.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "scenario.handler"
  filename         = "${local.build_dir}/demo_scenario.zip"
  source_code_hash = filebase64sha256("${local.build_dir}/demo_scenario.zip")
  memory_size      = 128
  timeout          = 900
  environment {
    variables = { TARGET_FUNCTION = aws_lambda_function.demo_orders_api.function_name }
  }
  depends_on = [aws_cloudwatch_log_group.demo_scenario]
}

resource "aws_lambda_function_event_invoke_config" "demo_scenario" {
  function_name          = aws_lambda_function.demo_scenario.function_name
  maximum_retry_attempts = 0
}

# Weekly partial scenario keeps a fresh live incident available (1-minute metrics expire after 15 days).
resource "aws_cloudwatch_event_rule" "weekly_scenario" {
  name                = "${local.prefix}-weekly-demo-scenario"
  description         = "Runs the controlled demo incident weekly"
  schedule_expression = "cron(0 3 ? * MON *)"
  state               = var.weekly_scenario_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "weekly_scenario" {
  rule  = aws_cloudwatch_event_rule.weekly_scenario.name
  arn   = aws_lambda_function.demo_scenario.arn
  input = jsonencode({ mode = "partial" })
}

resource "aws_lambda_permission" "weekly_scenario" {
  statement_id  = "AllowWeeklySchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.demo_scenario.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_scenario.arn
}
