# The farmer profile -> Farmer registry migration, as a one-off job image.
#
# It is built on the staff-api image the target registry already runs, which
# has the registry and its Farmer extension installed: the migration writes
# through those models, at that version, and carries no copy of them. Added
# here: this code, openpyxl for the Excel reports, and the country pack (old
# location codes -> P-codes, and the code lists' names).
#
#   docker build --build-arg REGISTRY_IMAGE=<the registry's staff-api image:tag> \
#     -t <registry>/farmer-profile-migration:<tag> .
#
# Run (README.md, deploy/job.yaml): it takes only addresses.
#   SOURCE_DSN  farmer profile's Odoo database (read only), libpq form
#   TARGET_DSN  the registry database, SQLAlchemy form (postgresql+psycopg2://...)
#   MDS_API_URL, MDS_TOKEN_URL, MDS_CLIENT_ID, MDS_CLIENT_SECRET
#               the Master Data Service: only codes and locations it has are migrated
#   /out        a volume: one folder per run with the log and the reports
ARG REGISTRY_IMAGE
FROM ${REGISTRY_IMAGE}

RUN pip install --no-cache-dir openpyxl==3.1.5

# The pack at the commit the registry's db-seed pins (OPENG2P_DATA_REF in its
# docker/db-seed/Dockerfile): the codes must be the ones the registry was seeded with.
ARG OPENG2P_DATA_REPO=https://github.com/Centre-for-Open-Societal-Systems/openg2p-data.git
ARG OPENG2P_DATA_REF=db3e2ff6e9cc764648c1348708c37cfec8e941c3
RUN mkdir -p /pack && cd /pack \
    && git init -q && git remote add origin ${OPENG2P_DATA_REPO} \
    && git fetch -q --depth 1 origin ${OPENG2P_DATA_REF} && git checkout -q FETCH_HEAD \
    && echo ${OPENG2P_DATA_REF} > /pack/REF && rm -rf .git

COPY . /migration/
WORKDIR /migration
ENV PYTHONPATH=/migration PACK_ROOT=/pack/packs REPORT_DIR=/out PYTHONUNBUFFERED=1
VOLUME /out

# migrate.py (default) or verify.py:  docker run ... <image> verify.py
ENTRYPOINT ["python"]
CMD ["migrate.py", "--help"]
