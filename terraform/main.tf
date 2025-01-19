terraform {
  required_providers {
    yandex = {
      source = "yandex-cloud/yandex"
    }
  }
  required_version = ">= 0.13"
}

variable "cloud_id" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "telegram_api_key" {
  type = string
}

provider "yandex" {
  cloud_id = var.cloud_id
  folder_id = var.folder_id
  service_account_key_file = "/Users/rustamshayk/.yc-keys/key.json"
}

resource "yandex_iam_service_account" "service-account-tg" {
  name = "service-account-tg"
  folder_id = var.folder_id
}

resource "yandex_iam_service_account_static_access_key" "static-access-key" {
  service_account_id = yandex_iam_service_account.service-account-tg.id
}

resource "yandex_resourcemanager_folder_iam_binding" "mount-iam" {
  folder_id = var.folder_id
  role = "editor"

  members = [
    "serviceAccount:${yandex_iam_service_account.service-account-tg.id}",
  ]
}

resource "archive_file" "face-detection" {
  type = "zip"
  output_path = "face_detection.zip"
  source_dir = "face_detection"
}

resource "yandex_storage_bucket" "photo-bucket" {
  bucket = "vvot17-photo"
  folder_id = var.folder_id
}

resource "yandex_function" "face-detection" {
  name = "vvot17-face-detection"
  user_hash = archive_file.face-detection.output_sha256
  runtime = "python39"
  entrypoint = "main.handler"
  memory = 128
  execution_timeout = 30
  environment = {
    "QUEUE_URL" = yandex_message_queue.task_queue.id,
    "AWS_ACCESS_KEY_ID" = yandex_iam_service_account_static_access_key.static-access-key.access_key
    "AWS_SECRET_ACCESS_KEY" = yandex_iam_service_account_static_access_key.static-access-key.secret_key,
    "GATEWAY_URL" = yandex_api_gateway.api-gateway.domain
    "PHOTOS_BUCKET_NAME" = yandex_storage_bucket.photo-bucket.bucket
  }

  service_account_id = yandex_iam_service_account.service-account-tg.id

  storage_mounts {
    mount_point_name = "images"
    bucket = yandex_storage_bucket.photo-bucket.bucket
    prefix = ""
  }

  content {
    zip_filename = archive_file.face-detection.output_path
  }
}

resource "yandex_function_trigger" "input_trigger" {
  name = "vvot17-photo"
  function {
    id = yandex_function.face-detection.id
    service_account_id = yandex_iam_service_account.service-account-tg.id
    retry_attempts = 2
    retry_interval = 10
  }
  object_storage {
    bucket_id = yandex_storage_bucket.photo-bucket.id
    suffix = ".jpg"
    create = true
    update = false
    delete = false
    batch_cutoff = 2
  }
}

resource "yandex_message_queue" "task_queue" {
  name = "vvot17-task"
  visibility_timeout_seconds = 600
  receive_wait_time_seconds = 20
  message_retention_seconds = 600
  access_key = yandex_iam_service_account_static_access_key.static-access-key.access_key
  secret_key = yandex_iam_service_account_static_access_key.static-access-key.secret_key
}

resource "yandex_storage_bucket" "faces-bucket" {
  bucket = "vvot17-faces"
  folder_id = var.folder_id
}

resource "archive_file" "face_cut" {
  type = "zip"
  output_path = "face_cut.zip"
  source_dir = "face_cut"
}

resource "yandex_function" "face-cut" {
  name = "vvot17-face-cut"
  user_hash = archive_file.face_cut.output_sha256
  runtime = "python39"
  entrypoint = "main.handler"
  memory = 128
  execution_timeout = 30
  environment = {
    "DB_URL" = yandex_ydb_database_serverless.database.ydb_full_endpoint
    "AWS_ACCESS_KEY_ID" = yandex_iam_service_account_static_access_key.static-access-key.access_key
    "AWS_SECRET_ACCESS_KEY" = yandex_iam_service_account_static_access_key.static-access-key.secret_key
    "PHOTOS_BUCKET_NAME" = yandex_storage_bucket.photo-bucket.bucket
    "FACES_BUCKET_NAME" = yandex_storage_bucket.faces-bucket.bucket
  }

  service_account_id = yandex_iam_service_account.service-account-tg.id

  storage_mounts {
    mount_point_name = "images"
    bucket = yandex_storage_bucket.photo-bucket.bucket
    prefix = ""
  }

  storage_mounts {
    mount_point_name = "faces"
    bucket = yandex_storage_bucket.faces-bucket.bucket
    prefix = ""
  }

  content {
    zip_filename = archive_file.face_cut.output_path
  }
}

resource "yandex_function_trigger" "task_trigger" {
  name = "vvot17-task"

  message_queue {
    queue_id = yandex_message_queue.task_queue.arn
    batch_cutoff = "5"
    batch_size = "5"
    service_account_id = yandex_iam_service_account.service-account-tg.id
  }
  function {
    id = yandex_function.face-cut.id
    service_account_id = yandex_iam_service_account.service-account-tg.id
  }
}

resource "yandex_api_gateway" "api-gateway" {
  name        = "vvot17-apigw"
  labels = {
    label = "label"
    empty-label = ""
  }
  spec = <<-EOT
    openapi: "3.0.0"
    info:
      version: 1.0.0
      title: API Gateway
    paths:
      /:
        get:
          parameters:
            - name: face
              in: query
              required: false
              schema:
                type: string
            - name: image
              in: query
              required: false
              schema:
                type: string
          responses:
            "200":
              description: File
              content:
                image/jpeg:
                  schema:
                    type: string
                    format: binary
          x-yc-apigateway-integration:
            type: cloud_functions
            payload_format_version: '0.1'
            function_id: ${yandex_function.api-gw.id}
            tag: $latest
            service_account_id: ${yandex_iam_service_account.service-account-tg.id}
  EOT
}

resource "yandex_ydb_database_serverless" "database" {
  name = "vvot17-db-photo-face"
  deletion_protection = false

  serverless_database {
    enable_throttling_rcu_limit = false
    provisioned_rcu_limit = 10
    storage_size_limit = 50
    throttling_rcu_limit = 0
  }
}

resource "yandex_ydb_table" "image_faces_table" {
  path = "image_faces"
  connection_string = yandex_ydb_database_serverless.database.ydb_full_endpoint

  column {
    name = "face_id"
    type = "String"
    not_null = true
  }
  column {
    name = "image_id"
    type = "String"
    not_null = true
  }

  primary_key = ["face_id"]
}

resource "yandex_ydb_table" "face_names_table" {
  path = "face_names"
  connection_string = yandex_ydb_database_serverless.database.ydb_full_endpoint

  column {
    name = "face_id"
    type = "String"
    not_null = true
  }
  column {
    name = "face_name"
    type = "String"
    not_null = false
  }

  primary_key = ["face_id"]
}

resource "archive_file" "bot" {
  type = "zip"
  output_path = "bot.zip"
  source_dir = "bot"
}

resource "yandex_function_iam_binding" "function-iam" {
  function_id = yandex_function.bot.id
  role = "serverless.functions.invoker"

  members = [
    "system:allUsers",
  ]
}

resource "yandex_function" "bot" {
  name = "vvot17-boot"
  user_hash = archive_file.bot.output_sha256
  runtime = "python39"
  entrypoint = "main.handler"
  memory = 128
  execution_timeout = 30
  environment = {
    "TELEGRAM_API_KEY" = var.telegram_api_key,
    "DB_URL" = yandex_ydb_database_serverless.database.ydb_full_endpoint,
    "GATEWAY_URL" = yandex_api_gateway.api-gateway.domain
  }
  service_account_id = yandex_iam_service_account.service-account-tg.id

  storage_mounts {
    mount_point_name = "faces"
    bucket = yandex_storage_bucket.faces-bucket.bucket
    prefix = ""
  }

  storage_mounts {
    mount_point_name = "images"
    bucket = yandex_storage_bucket.photo-bucket.bucket
    prefix = ""
  }

  content {
    zip_filename = archive_file.bot.output_path
  }
}

resource "yandex_function" "api-gw" {
  name = "vvot17-api-gw"
  user_hash = archive_file.gw.output_sha256
  runtime = "python39"
  entrypoint = "main.handler"
  memory = 128
  execution_timeout = 30
  service_account_id = yandex_iam_service_account.service-account-tg.id

  storage_mounts {
    mount_point_name = "faces"
    bucket = yandex_storage_bucket.faces-bucket.bucket
    prefix = ""
  }

  storage_mounts {
    mount_point_name = "images"
    bucket = yandex_storage_bucket.photo-bucket.bucket
    prefix = ""
  }

  content {
    zip_filename = archive_file.gw.output_path
  }
}

resource "archive_file" "gw" {
  type = "zip"
  output_path = "api_gw.zip"
  source_dir = "api_gw"
}

resource "null_resource" "curl" {
  provisioner "local-exec" {
    command = "curl --insecure -X POST https://api.telegram.org/bot${var.telegram_api_key}/setWebhook?url=https://functions.yandexcloud.net/${yandex_function.bot.id}"
  }

  triggers = {
    destroy_var = var.telegram_api_key
  }

  provisioner "local-exec" {
    when = destroy
    command = "curl --insecure -X POST https://api.telegram.org/bot${self.triggers.destroy_var}/deleteWebhook"
  }
}