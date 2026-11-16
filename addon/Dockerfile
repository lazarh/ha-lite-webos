ARG BUILD_FROM=alpine:3.20
FROM ${BUILD_FROM}

RUN apk add --no-cache nginx jq

COPY nginx.conf /etc/nginx/nginx.conf
COPY run.sh /run.sh
COPY webapp/ /usr/share/nginx/html/

RUN chmod +x /run.sh

EXPOSE 8099
ENTRYPOINT []
CMD [ "/run.sh" ]
