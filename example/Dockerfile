FROM public.ecr.aws/lambda/python:3.11

RUN yum update -y && \
    yum install -y strace && \
    yum clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}
COPY .env ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt

COPY lambda_function.py ${LAMBDA_TASK_ROOT}

RUN chmod +x /var/runtime/bootstrap

CMD [ "lambda_function.lambda_handler" ]
