# Workspace isolation smoke-test image, not an Astropy evaluation environment.
# Pi/Wasabi and model access will be integrated in a later stage.
FROM python:3.11-slim
RUN useradd --uid 10001 --create-home agent
USER agent
WORKDIR /workspace
CMD ["python", "--version"]
