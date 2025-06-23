FROM public.ecr.aws/lambda/python:3.9

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy function code
COPY hourly_weather.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "hourly_weather.lambda_handler" ] 