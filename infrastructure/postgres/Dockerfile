FROM postgres:17.11-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
# The upstream entrypoint only uses gosu when started as root. Start as postgres
# directly and remove the unused helper (whose bundled Go runtime is vulnerable).
RUN rm /usr/local/bin/gosu
USER 70:70
