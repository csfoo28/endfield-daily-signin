FROM python:3.12-alpine
WORKDIR /app
COPY endfield_checkin.py .
USER nobody
ENTRYPOINT ["python3", "-u", "/app/endfield_checkin.py"]
CMD ["--loop"]
