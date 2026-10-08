ARG BUILD_FROM
FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG WAMF_REPO
ARG WAMF_REF

# The add-on build context is only this folder, so the app source is fetched
# from the repository. BUILD_VERSION is echoed so a version bump always
# re-fetches instead of reusing a cached layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git tzdata ca-certificates \
    && echo "Building Who's At My Feeder ${BUILD_VERSION} from ${WAMF_REPO}@${WAMF_REF}" \
    && git clone --depth 1 --branch "${WAMF_REF}" "${WAMF_REPO}" /app \
    && pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y git && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /app/.git

COPY run.py /run.py
WORKDIR /app
CMD ["python", "/run.py"]
