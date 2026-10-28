FROM scratch
# run.py builds under umask 077; give the non-root user read and execute.
COPY --chmod=0555 release-probe /release-probe
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["/release-probe"]
