from haproxy
USER root
RUN apt update
RUN apt install curl -y
COPY haproxy.health_check /var/lib/haproxy/health_check
RUN chmod +x /var/lib/haproxy/health_check
USER haproxy
