# RabbitMQ Clustering 

We are using RabbitMQ as a message broker for Celery task execution. For our application, the task execution is of utmost importance for the sourcing events to work properly. So, for our RabbitMQ queue to be highly available, we are moving from single node RabbitMQ to a RabbitMQ cluster with 3 mirrored nodes.

## Pre-requisites

1. AWS CodePipeline
2. AWS CodeCommit
3. AWS CodeBuild
4. AWS S3
5. AWS CloudWatch
6. AWS Cloudformation
7. AWS EC2
8. AWS CloudMap
9. AWS EC2 Auto Scaling
10. AWS IAM - required only if need to create a new build project or pipeline

## How to deploy a RabbitMQ Cluster
We have already created a CodePipeline that deploys the whole stack using Cloudformation template in particular environment. If pipeline is not present, go to further sections for cloning/creating a new pipeline.

1. Verify if `config.json` is uploaded on S3 at location: `krinatisecrets/{environment}/queue-cluster/` and is in [correct and valid format](config-template.json)
2. Now, pushing `CodePipeline` Source branch code to `CodeCommit` should start the pipeline.
3. During manual approval stage, make sure to check output log of previous build stage and verify parameter values that would be passed to `Cloudformation` template in deploy stage and Approve/Reject accordingly
4. If the pipeline fails, watch Build logs and find the issue. If it succeeds, go to `Cloudformation` in AWS Console and watch the progress.

## How to clone an existing pipeline for deploying RabbitMQ Cluster in new environment 
If a pipeline does not exist for a particular target environment, a new pipeline can be created by cloning from existing pipeline.

After successful cloning,
1. `Stop Execution` of pipeline
2. Edit Pipeline by clicking on `Edit`
3. `Edit Build Stage` and Update the value for `Environment` under `Environment variables` to relevant value (`dev`/`test`/`prod`) and save
4. `Edit Deploy Stage` Update the value for `Environment` under `Environment variables` to relevant value (`dev`/`test`/`prod`) and save 
5. Finally, save all changes
6. Pipeline is ready for deployment!

## How to create a Pipeline for deploying RabbitMQ cluster from scratch
1. Click on `Create Pipeline` in CodePipeline
2. `Pipeline Settings stage`
   - Enter Pipeline Name, ideally in format (Env_RabbitMQ_Cluster)
   - Click on `Next`
3. `Source Stage`
   - Add `AWS CodeCommit` as Source Provider
   - Repository name as `sourcing`
   - Relevant branch name, ideally `master`
   - Select `Full Clone` for Output artifact format
   - Click on `Next`
4. `Build Stage`
   - Add `AWS CodeBuild` as Source Provider
   - Select `Validate_Queue_Config` build project
        - If `Validate_Queue_Config` does not exist
           - Click on `Create Project`
           - Enter Project Name `Validate_Queue_Config`
           - Check `Restrict number of concurrent builds this project can start` checkbox
           - Use `Managed Image`
           - Select `Amazon Linux 2` as operating system
           - Runtime(s) - `Standard`
           - Image - any latest version
           - Use Existing Service Role with arn `arn:aws:iam::979457015250:role/service-role/Deploy_RabbitMQ_Cluster_Using_Cloudformation`
           - Change default timeout to max 10 minutes
           - `Insert build commands` using Editor
             ```
             version: 0.2

             phases:
               build:
                 commands:
                   - aws s3 cp s3://krinatisecrets/${Environment}/queue-cluster/config.json .
                   - cat config.json
             ```
             - Under Cloudwatch logs, enter `krinatibuild` GroupName and `Deploy_RabbitMQ_Cluster` as Stream name
             - Click on `Continue to CodePipeline`

   - Click on `Add Environment Variables`
   - Add name `Environment` and relevant value from `dev`/`test`/`prod` in Plaintext type
   - Click on `Next`
5. `Deploy Stage`
   - Click on `Skip deploy stage`
6. `Review`
   - Click on `Create Pipeline`
7. Now, pipeline should have started, click `Stop execution` and abandon execution
8. `Edit` Pipeline
9. `Add Stage` `Approval` after `Build` stage
   - Click on `Add action group`
   - Select `Manual approval` as Action provider
   - Click on `Done`
10. Add Stage `Deploy` after `Approval` stage
    - Click on `Add action group`
    - Select `AWS CodeBuild` as Action provider
    - Select `SourceArtifact` for Input artifacts
    - Select `Deploy_RabbitMQ_Cluster` build project
        - If `Deploy_RabbitMQ_Cluster` does not exist
           - Click on `Create Project`
           - Enter Project Name `Deploy_RabbitMQ_Cluster`
           - Check `Restrict number of concurrent builds this project can start` checkbox
           - Use `Managed Image`
           - Select `Amazon Linux 2` as operating system
           - Runtime(s) - `Standard`
           - Image - any latest version
           - Use Existing Service Role with arn `arn:aws:iam::979457015250:role/service-role/Deploy_RabbitMQ_Cluster_Using_Cloudformation`
           - Change default timeout to max 10 minutes
           - `Insert build commands` using Editor
             ```
             version: 0.2

             phases:
               pre_build:
                 commands:
                   - cd repositories/queue-cluster
                   - aws s3 cp s3://krinatisecrets/${Environment}/queue-cluster/config.json .
                   - aws s3 mb s3://krinati-rabbitmq-cluster-${Environment}
               build:
                 commands:
                   - SAM_PARAMETERS=$( cat config.json | jq -r '.[] | "\(.ParameterKey)=\(.ParameterValue)"' )
                   - echo $SAM_PARAMETERS
                   - sam build && sam deploy --stack-name RabbitMQ-Cluster-${Environment} --s3-bucket krinati-rabbitmq-cluster-${Environment} --no-confirm-changeset --capabilities CAPABILITY_IAM --parameter-overrides $SAM_PARAMETERS
             ```
             - Under Cloudwatch logs, enter `krinatibuild` GroupName and `Deploy_RabbitMQ_Cluster` as Stream name
             - Click on `Continue to CodePipeline`
    - Click on `Add Environment Variables`
    - Add name `Environment` and relevant value from `dev`/`test`/`prod` in Plaintext type
    - Click on `Done`
11. Finally, save all the changes
12. Pipeline is ready for deployment!
