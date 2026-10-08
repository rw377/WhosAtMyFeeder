# The app needs Python 3.8 on Debian (tflite_support has no Alpine wheels), so
# this deliberately does not build FROM the Home Assistant base image that the
# Supervisor passes in as BUILD_FROM.
FROM python:3.8-slim-bookworm

ARG BUILD_VERSION
ARG WAMF_REPO=https://github.com/rw377/WhosAtMyFeeder
ARG WAMF_REF=master

# The add-on build context is only this folder, so the app source is fetched
# from the repository. BUILD_VERSION is echoed so a version bump always
# re-fetches instead of reusing a cached layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tzdata ca-certificates libusb-1.0-0 \
    && echo "Building Who's At My Feeder ${BUILD_VERSION} from ${WAMF_REPO}@${WAMF_REF}" \
    && git clone --depth 1 --branch "${WAMF_REF}" "${WAMF_REPO}" /app \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y git && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /app/.git

COPY run.py /run.py
WORKDIR /app
CMD ["python", "/run.py"]
