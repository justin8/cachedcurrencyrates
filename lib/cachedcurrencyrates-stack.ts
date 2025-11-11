import * as cdk from "aws-cdk-lib/core";
import { Construct } from "constructs";
import {
  aws_apigatewayv2 as apigwv2,
  aws_lambda as lambda,
  aws_dynamodb as dynamodb,
} from "aws-cdk-lib";
import { HttpLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";

export class CachedcurrencyratesStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const table = new dynamodb.Table(this, "CacheTable", {
      partitionKey: {
        name: "requestHash",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PROVISIONED,
      readCapacity: 2,
      writeCapacity: 2,
    });

    const backend = new PythonFunction(this, "backend", {
      entry: "src/lambda",
      runtime: lambda.Runtime.PYTHON_3_12,
      index: "index.py",
      handler: "handler",
      environment: {
        TABLE_NAME: table.tableName,
      },
    });

    table.grantReadWriteData(backend);

    const httpApi = new apigwv2.HttpApi(this, "HttpApi", {
      apiName: "CachedCurrencyRatesApi",
    });

    const integration = new HttpLambdaIntegration("LambdaIntegration", backend);

    httpApi.addRoutes({
      path: "/{proxy+}",
      methods: [apigwv2.HttpMethod.ANY],
      integration: integration,
    });

    new cdk.CfnOutput(this, "ApiUrl", {
      value: httpApi.url!,
      description: "HTTP API URL",
    });
  }
}
