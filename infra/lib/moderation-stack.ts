import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as apigwv2_integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as apigwv2_authorizers from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as logs from "aws-cdk-lib/aws-logs";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import { SqsEventSource } from "aws-cdk-lib/aws-lambda-event-sources";
import { Construct } from "constructs";

export class ModerationStack extends cdk.Stack {
  /** VPC for RDS and Lambda */
  public readonly vpc: ec2.Vpc;
  /** Security group allowing Lambda to access RDS */
  public readonly lambdaSg: ec2.SecurityGroup;
  /** RDS PostgreSQL instance */
  public readonly database: rds.DatabaseInstance;
  /** SQS batch test queue */
  public readonly batchTestQueue: sqs.Queue;
  /** SQS dead letter queue for failed batch test messages */
  public readonly batchTestDlq: sqs.Queue;
  /** S3 bucket for frontend static assets */
  public readonly frontendBucket: s3.Bucket;
  /** S3 bucket for test suite files */
  public readonly testSuitesBucket: s3.Bucket;
  /** Lambda: moderation API handler */
  public readonly moderationApiFunction: lambda.Function;
  /** Lambda: admin API handler */
  public readonly adminApiFunction: lambda.Function;
  /** Lambda: batch test SQS worker */
  public readonly batchTestWorkerFunction: lambda.Function;
  /** CloudFront distribution for frontend */
  public readonly distribution: cloudfront.Distribution;
  /** REST API Gateway */
  public readonly api: apigw.RestApi;
  /** Cognito User Pool for admin authentication */
  public readonly userPool: cognito.UserPool;
  /** Cognito App Client for SPA */
  public readonly userPoolClient: cognito.UserPoolClient;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // ── VPC ──────────────────────────────────────────────────
    this.vpc = new ec2.Vpc(this, "ModerationVpc", {
      maxAzs: 2,
      subnetConfiguration: [
        { name: "Public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        {
          name: "Private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
      ],
    });

    // ── Security Groups ─────────────────────────────────────
    this.lambdaSg = new ec2.SecurityGroup(this, "LambdaSg", {
      vpc: this.vpc,
      description: "Security group for Lambda functions",
      allowAllOutbound: true,
    });

    const dbSg = new ec2.SecurityGroup(this, "DatabaseSg", {
      vpc: this.vpc,
      description: "Security group for RDS PostgreSQL",
      allowAllOutbound: false,
    });
    dbSg.addIngressRule(
      this.lambdaSg,
      ec2.Port.tcp(5432),
      "Allow Lambda access to PostgreSQL"
    );

    // ── RDS PostgreSQL ──────────────────────────────────────
    this.database = new rds.DatabaseInstance(this, "ModerationDb", {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.T3,
        ec2.InstanceSize.MICRO
      ),
      vpc: this.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSg],
      databaseName: "moderation",
      credentials: rds.Credentials.fromGeneratedSecret("moderation_admin"),
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      deletionProtection: false,
    });

    // ── SQS Queues ──────────────────────────────────────────
    this.batchTestDlq = new sqs.Queue(this, "BatchTestDlq", {
      queueName: "moderation-batch-test-dlq",
      retentionPeriod: cdk.Duration.days(14),
    });

    this.batchTestQueue = new sqs.Queue(this, "BatchTestQueue", {
      queueName: "moderation-batch-test",
      visibilityTimeout: cdk.Duration.minutes(15),
      deadLetterQueue: {
        queue: this.batchTestDlq,
        maxReceiveCount: 3,
      },
    });

    // ── S3 Buckets ──────────────────────────────────────────
    this.frontendBucket = new s3.Bucket(this, "FrontendBucket", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    this.testSuitesBucket = new s3.Bucket(this, "TestSuitesBucket", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // ── CloudFront + OAI (Frontend) ────────────────────────
    const oai = new cloudfront.OriginAccessIdentity(this, "FrontendOai");
    this.frontendBucket.grantRead(oai);

    this.distribution = new cloudfront.Distribution(this, "FrontendDist", {
      defaultBehavior: {
        origin:
          origins.S3BucketOrigin.withOriginAccessIdentity(
            this.frontendBucket,
            { originAccessIdentity: oai }
          ),
        viewerProtocolPolicy:
          cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
      },
      defaultRootObject: "index.html",
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: "/index.html",
        },
      ],
    });

    // ── Cognito User Pool (Admin Auth) ────────────────────
    this.userPool = new cognito.UserPool(this, "AdminUserPool", {
      userPoolName: "moderation-admin-pool",
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      passwordPolicy: {
        minLength: 8,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.userPoolClient = this.userPool.addClient("AdminSpaClient", {
      userPoolClientName: "moderation-admin-spa",
      generateSecret: false,
      authFlows: {
        userSrp: true,
        adminUserPassword: true,
      },
    });

    // ── Shared Lambda environment variables ─────────────────
    const sharedEnv: Record<string, string> = {
      DATABASE_SECRET_ARN: this.database.secret!.secretArn,
      SQS_QUEUE_URL: this.batchTestQueue.queueUrl,
      S3_TEST_SUITES_BUCKET: this.testSuitesBucket.bucketName,
      MODERATION_COGNITO_USER_POOL_ID: this.userPool.userPoolId,
      MODERATION_COGNITO_APP_CLIENT_ID: this.userPoolClient.userPoolClientId,
      MODERATION_COGNITO_REGION: this.region,
    };

    const privateSubnets: ec2.SubnetSelection = {
      subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
    };

    // ── Lambda: Moderation API ──────────────────────────────
    this.moderationApiFunction = new lambda.Function(this, "ModerationApiFn", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "app.main.handler",
      code: lambda.Code.fromAsset("../backend/package"),
      memorySize: 512,
      timeout: cdk.Duration.seconds(60),
      vpc: this.vpc,
      vpcSubnets: privateSubnets,
      securityGroups: [this.lambdaSg],
      environment: sharedEnv,
      tracing: lambda.Tracing.ACTIVE,
    });

    // ── Lambda: Admin API ───────────────────────────────────
    this.adminApiFunction = new lambda.Function(this, "AdminApiFn", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "app.main.handler",
      code: lambda.Code.fromAsset("../backend/package"),
      memorySize: 512,
      timeout: cdk.Duration.seconds(60),
      vpc: this.vpc,
      vpcSubnets: privateSubnets,
      securityGroups: [this.lambdaSg],
      environment: sharedEnv,
      tracing: lambda.Tracing.ACTIVE,
    });

    // ── Lambda: Batch Test Worker ───────────────────────────
    this.batchTestWorkerFunction = new lambda.Function(
      this,
      "BatchTestWorkerFn",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "app.services.batch_test_worker.handler",
        code: lambda.Code.fromAsset("../backend/package"),
        memorySize: 1024,
        timeout: cdk.Duration.minutes(15),
        vpc: this.vpc,
        vpcSubnets: privateSubnets,
        securityGroups: [this.lambdaSg],
        environment: sharedEnv,
        tracing: lambda.Tracing.ACTIVE,
      }
    );

    // ── SQS → Lambda event source mapping ───────────────────
    this.batchTestWorkerFunction.addEventSource(
      new SqsEventSource(this.batchTestQueue, {
        batchSize: 1,
      })
    );

    // ── Permissions: RDS Secret ─────────────────────────────
    this.database.secret!.grantRead(this.moderationApiFunction);
    this.database.secret!.grantRead(this.adminApiFunction);
    this.database.secret!.grantRead(this.batchTestWorkerFunction);

    // ── Permissions: S3 ─────────────────────────────────────
    this.testSuitesBucket.grantReadWrite(this.adminApiFunction);
    this.testSuitesBucket.grantRead(this.batchTestWorkerFunction);

    // ── Permissions: SQS ────────────────────────────────────
    this.batchTestQueue.grantSendMessages(this.adminApiFunction);
    // (consume permission is auto-granted by SqsEventSource)

    // ── Permissions: Bedrock ────────────────────────────────
    const bedrockPolicy = new iam.PolicyStatement({
      actions: ["bedrock:InvokeModel"],
      resources: ["*"],
    });
    this.moderationApiFunction.addToRolePolicy(bedrockPolicy);
    this.adminApiFunction.addToRolePolicy(bedrockPolicy);
    this.batchTestWorkerFunction.addToRolePolicy(bedrockPolicy);

    // ── CloudWatch Log Groups (14-day retention) ────────────
    new logs.LogGroup(this, "ModerationApiLogGroup", {
      logGroupName: `/aws/lambda/${this.moderationApiFunction.functionName}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new logs.LogGroup(this, "AdminApiLogGroup", {
      logGroupName: `/aws/lambda/${this.adminApiFunction.functionName}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new logs.LogGroup(this, "BatchTestWorkerLogGroup", {
      logGroupName: `/aws/lambda/${this.batchTestWorkerFunction.functionName}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // ── CloudWatch Alarms (Lambda errors) ───────────────────
    new cloudwatch.Alarm(this, "ModerationApiErrorAlarm", {
      alarmName: "ModerationApi-Errors",
      metric: this.moderationApiFunction.metricErrors({
        period: cdk.Duration.minutes(5),
      }),
      threshold: 5,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    });

    new cloudwatch.Alarm(this, "AdminApiErrorAlarm", {
      alarmName: "AdminApi-Errors",
      metric: this.adminApiFunction.metricErrors({
        period: cdk.Duration.minutes(5),
      }),
      threshold: 5,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    });

    new cloudwatch.Alarm(this, "BatchTestWorkerErrorAlarm", {
      alarmName: "BatchTestWorker-Errors",
      metric: this.batchTestWorkerFunction.metricErrors({
        period: cdk.Duration.minutes(5),
      }),
      threshold: 5,
      evaluationPeriods: 1,
      comparisonOperator:
        cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
    });

    // ── API Gateway (REST) ──────────────────────────────────
    this.api = new apigw.RestApi(this, "ModerationApi", {
      restApiName: "ModerationService",
      description: "Content moderation REST API",
      deployOptions: { stageName: "prod" },
    });

    // -- API Key + Usage Plan for moderation API --
    const apiKey = this.api.addApiKey("ModerationApiKey");
    const usagePlan = this.api.addUsagePlan("ModerationUsagePlan", {
      name: "ModerationUsagePlan",
      throttle: { rateLimit: 50, burstLimit: 100 },
    });
    usagePlan.addApiKey(apiKey);
    usagePlan.addApiStage({ stage: this.api.deploymentStage });

    // -- Lambda integrations --
    const moderationIntegration = new apigw.LambdaIntegration(
      this.moderationApiFunction
    );
    const adminIntegration = new apigw.LambdaIntegration(
      this.adminApiFunction
    );

    // -- /api/v1/* → moderationApi (API Key required) --
    const apiResource = this.api.root.addResource("api");
    const v1Resource = apiResource.addResource("v1");
    const v1Proxy = v1Resource.addProxy({
      defaultIntegration: moderationIntegration,
      anyMethod: true,
      defaultMethodOptions: { apiKeyRequired: true },
    });

    // -- /api/admin/* → adminApi (Cognito authorizer) --
    const cognitoAuthorizer = new apigw.CognitoUserPoolsAuthorizer(
      this,
      "AdminCognitoAuthorizer",
      {
        cognitoUserPools: [this.userPool],
        authorizerName: "AdminCognitoAuthorizer",
      }
    );

    const adminResource = apiResource.addResource("admin");

    // Enable CORS on admin resource (OPTIONS must bypass Cognito authorizer)
    adminResource.addCorsPreflight({
      allowOrigins: apigw.Cors.ALL_ORIGINS,
      allowMethods: apigw.Cors.ALL_METHODS,
      allowHeaders: [
        "Content-Type",
        "Authorization",
        "X-Amz-Date",
        "X-Amz-Security-Token",
      ],
    });

    const adminProxy = adminResource.addProxy({
      defaultIntegration: adminIntegration,
      anyMethod: true,
      defaultMethodOptions: {
        authorizer: cognitoAuthorizer,
        authorizationType: apigw.AuthorizationType.COGNITO,
      },
    });

    // CORS on the proxy resource too
    adminProxy.addCorsPreflight({
      allowOrigins: apigw.Cors.ALL_ORIGINS,
      allowMethods: apigw.Cors.ALL_METHODS,
      allowHeaders: [
        "Content-Type",
        "Authorization",
        "X-Amz-Date",
        "X-Amz-Security-Token",
      ],
    });

    // ── Stack outputs ───────────────────────────────────────

    // Add CORS headers to ALL API Gateway error responses (4xx, 5xx)
    // This ensures CORS errors don't mask the real error in the browser
    const corsHeaders = {
      "Access-Control-Allow-Origin": "'*'",
      "Access-Control-Allow-Headers": "'Content-Type,Authorization,X-API-Key,X-Amz-Date,X-Amz-Security-Token'",
      "Access-Control-Allow-Methods": "'GET,POST,PUT,DELETE,OPTIONS'",
    };

    this.api.addGatewayResponse("Default4xx", {
      type: apigw.ResponseType.DEFAULT_4XX,
      responseHeaders: corsHeaders,
    });

    this.api.addGatewayResponse("Default5xx", {
      type: apigw.ResponseType.DEFAULT_5XX,
      responseHeaders: corsHeaders,
    });

    // ── HTTP API Gateway v2 (parallel, for latency comparison) ────
    // HTTP API has lower latency (~50-100ms) and cost than REST API.
    // API key check is done via a simple Lambda Authorizer (header match).
    // The HTTP API accepts the same API key as the REST API for client compatibility.

    // Shared API key — must match the REST API key that clients already use.
    // Pass via CDK context: `cdk deploy -c httpApiKey=<your-key>`
    // or via environment variable: `HTTP_API_KEY=<your-key> cdk deploy`
    // Falls back to an environment variable at deploy time so no secret lives in source.
    const httpApiKey =
      this.node.tryGetContext("httpApiKey") ||
      process.env.HTTP_API_KEY ||
      "REPLACE_WITH_YOUR_API_KEY_AT_DEPLOY_TIME";

    if (httpApiKey === "REPLACE_WITH_YOUR_API_KEY_AT_DEPLOY_TIME") {
      // Deploy will still succeed but Lambda authorizer will reject all requests
      // until httpApiKey context or HTTP_API_KEY env var is set.
      cdk.Annotations.of(this).addWarning(
        "HTTP API key not configured. Pass -c httpApiKey=<key> or set HTTP_API_KEY env var."
      );
    }

    const authorizerFn = new lambda.Function(this, "HttpApiAuthFn", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "index.handler",
      code: lambda.Code.fromInline(`
import os

EXPECTED_KEY = os.environ["API_KEY"]

def handler(event, context):
    """Simple API key check for HTTP API v2 (simple response format)."""
    headers = event.get("headers") or {}
    provided = headers.get("x-api-key") or headers.get("X-API-Key") or ""
    return {"isAuthorized": provided == EXPECTED_KEY}
`),
      memorySize: 128,
      timeout: cdk.Duration.seconds(3),
      environment: { API_KEY: httpApiKey },
    });

    const httpApi = new apigwv2.HttpApi(this, "ModerationHttpApi", {
      apiName: "ModerationServiceHttp",
      description: "Content moderation HTTP API (lower latency alternative)",
      corsPreflight: {
        allowOrigins: ["*"],
        allowMethods: [
          apigwv2.CorsHttpMethod.GET,
          apigwv2.CorsHttpMethod.POST,
          apigwv2.CorsHttpMethod.PUT,
          apigwv2.CorsHttpMethod.DELETE,
          apigwv2.CorsHttpMethod.OPTIONS,
        ],
        allowHeaders: [
          "Content-Type",
          "Authorization",
          "X-API-Key",
          "X-Amz-Date",
          "X-Amz-Security-Token",
        ],
      },
    });

    const apiKeyAuthorizer = new apigwv2_authorizers.HttpLambdaAuthorizer(
      "ApiKeyAuthorizer",
      authorizerFn,
      {
        authorizerName: "ApiKeyAuthorizer",
        identitySource: ["$request.header.X-API-Key"],
        responseTypes: [apigwv2_authorizers.HttpLambdaResponseType.SIMPLE],
        resultsCacheTtl: cdk.Duration.minutes(5),
      }
    );

    const moderationV2Integration =
      new apigwv2_integrations.HttpLambdaIntegration(
        "ModerationV2Integration",
        this.moderationApiFunction
      );

    // /api/v1/{proxy+} on HTTP API — API Key authorized
    httpApi.addRoutes({
      path: "/api/v1/{proxy+}",
      methods: [
        apigwv2.HttpMethod.GET,
        apigwv2.HttpMethod.POST,
        apigwv2.HttpMethod.PUT,
        apigwv2.HttpMethod.DELETE,
      ],
      integration: moderationV2Integration,
      authorizer: apiKeyAuthorizer,
    });

    // /health on HTTP API — no auth
    httpApi.addRoutes({
      path: "/health",
      methods: [apigwv2.HttpMethod.GET],
      integration: moderationV2Integration,
    });

    new cdk.CfnOutput(this, "HttpApiUrl", {
      value: httpApi.apiEndpoint,
      description: "HTTP API v2 endpoint (lower-latency alternative)",
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: this.api.url,
      description: "API Gateway endpoint URL",
    });
    new cdk.CfnOutput(this, "ApiKeyId", {
      value: apiKey.keyId,
      description: "API Key ID (retrieve value from AWS Console)",
    });
    new cdk.CfnOutput(this, "FrontendUrl", {
      value: `https://${this.distribution.distributionDomainName}`,
      description: "CloudFront distribution URL for frontend",
    });
    new cdk.CfnOutput(this, "FrontendBucketName", {
      value: this.frontendBucket.bucketName,
      description: "S3 bucket name for frontend static assets",
    });
    new cdk.CfnOutput(this, "DistributionId", {
      value: this.distribution.distributionId,
      description: "CloudFront distribution ID for cache invalidation",
    });
    new cdk.CfnOutput(this, "UserPoolId", {
      value: this.userPool.userPoolId,
      description: "Cognito User Pool ID",
    });
    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: this.userPoolClient.userPoolClientId,
      description: "Cognito App Client ID",
    });
  }
}
