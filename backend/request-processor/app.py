import json
import boto3
import io
import logging
import os
from contextlib import closing
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

comprehend = boto3.client('comprehend')
polly = boto3.client('polly')
s3 = boto3.client('s3')
sns = boto3.client('sns')
connect = boto3.client('connect', region_name ='eu-central-1')

languages = {'pl':'Maja','en':'Matthew','de':'Vicki','fr':'Celine','ja':'Mizuki'}

def lambda_handler(event, context):


    text = event["queryStringParameters"]["text"]
    phoneNumber = event["queryStringParameters"]["phoneNumber"]
    mode = event["queryStringParameters"]["mode"]

    logger.info('New Request!');
    logger.info('Text: %s', text);
    logger.info('Phone Number: %s', phoneNumber);
    logger.info('Mode: %s', mode);

    # Detect language
    comprehend = boto3.client('comprehend')
    response = comprehend.detect_dominant_language(
        Text=text
    )

    if len(response['Languages']) != 1:
        language = "pl"
    else:
        language = response['Languages'][0]['LanguageCode']


    voice =  languages[language]

    logger.info('Language: %s', language);
    logger.info('Voice: %s', voice);

    # Using Amazon Polly service to convert text to speech
    response = polly.synthesize_speech(
        OutputFormat='mp3',
        Text=text,
        TextType='text',
        VoiceId=voice
    )

    file = str(uuid.uuid4()) + ".mp3";
    logger.info('File: %s', file);


    # Save audio on local directory
    if "AudioStream" in response:
        with closing(response["AudioStream"]) as stream:
            output = os.path.join("/tmp/", file)
            with open(output, "wb") as audioFile:
                audioFile.write(stream.read())


    s3.upload_file('/tmp/' + file, os.environ['BUCKET'], file)
    s3.put_object_acl(ACL='public-read', Bucket=os.environ['BUCKET'], Key = file)

    #Creating new record in DynamoDB table
    location = s3.get_bucket_location(Bucket=os.environ['BUCKET'])
    region = location['LocationConstraint']
    url_begining = "https://s3-" + str(region) + ".amazonaws.com/"
    url = url_begining + os.environ['BUCKET'] + "/" + file

    logger.info('URL: %s', url);

    #Adding information about new audio file to DynamoDB table
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(os.environ['TABLE'])
    table.put_item(
        Item={
            'file' : file,
            'text' : text,
            'language' : language,
            'voice' : voice,
            'url' : url,
            'phoneNumber' : phoneNumber,
            'mode' : mode
        }
    )

    if int(mode) == 1:
        logger.info('Sending SMS: %s', url);
        sns.publish( PhoneNumber=phoneNumber, Message=url, MessageAttributes={'AWS.SNS.SMS.SenderID': {'DataType': 'String', 'StringValue': "CHMURA"}, 'AWS.SNS.SMS.SMSType': {'DataType': 'String', 'StringValue': 'Promotional'}} );

    if int(mode) == 2:
        logger.info('Calling User');
        callUser(language, text, phoneNumber)



    return {
        'statusCode': 200,
        'body': json.dumps('OK')
    }

def callUser(language, text, phone):

    instanceId = '9ebe3d3d-e53c-4167-8764-582e82c68450'
    sourcePhoneNumber = '+48800088030'

    if language == 'pl':
        contactFlowId = 'b30ac8f2-9679-4b42-bd58-dc9ff3f08c48'

    if language == 'en':
        contactFlowId = '23b715cf-2c9f-453b-b521-1c7cb5e4cb2f'

    if language == 'de':
        contactFlowId = '3494e68b-fc90-4baf-bd62-8e925217204e'

    if language == 'fr':
        contactFlowId = 'db8307a3-9e9b-428c-9d59-5f3784358dfe'

    logger.info('Calling!');
    logger.info('Phone Number: %s ...', phone[0:9]);
    logger.info('Text: %s', text);
    logger.info('Language: %s', language);
    logger.info('Contact Flow ID: %s', contactFlowId);

    connect.start_outbound_voice_contact(
        DestinationPhoneNumber=phone,
        ContactFlowId=contactFlowId,
        InstanceId=instanceId,
        SourcePhoneNumber=sourcePhoneNumber,
        Attributes={
            'text': text
        }
    )
