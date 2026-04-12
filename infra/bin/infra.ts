#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { ModerationStack } from "../lib/moderation-stack";

const app = new cdk.App();

new ModerationStack(app, "ContentModerationStack", {
  description: "Content moderation system infrastructure",
});
