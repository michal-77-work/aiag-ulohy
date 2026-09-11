# LangFlow + MSSQL driver
#
# The stock `langflowai/langflow` image ships no MSSQL driver, so the
# "SQL Database" tool in `03-Agents/3-ai-agents/AI Agent - Tools.json`
# cannot connect to the ecommerce MSSQL server. This image adds
# Microsoft's ODBC driver and pyodbc on top of it.
#
# NOTE: since langflow 1.10.x the base image switched from Debian to
# Red Hat UBI (RHEL), which has no apt-get - only microdnf/rpm. The RHEL
# version is read from /etc/os-release so this keeps working if the base
# image's RHEL major version changes again.
FROM langflowai/langflow:latest

USER root

RUN RHEL_VERSION=$(grep VERSION_ID /etc/os-release | cut -d '"' -f 2 | cut -d '.' -f 1) \
    && curl -sSL -o /tmp/packages-microsoft-prod.rpm \
       https://packages.microsoft.com/config/rhel/${RHEL_VERSION}/packages-microsoft-prod.rpm \
    && rpm -i /tmp/packages-microsoft-prod.rpm \
    && rm -f /tmp/packages-microsoft-prod.rpm \
    && ACCEPT_EULA=Y microdnf install -y msodbcsql18 unixODBC-devel \
    && /app/.venv/bin/pip install --no-cache-dir pyodbc \
    && microdnf clean all \
    && rm -rf /var/cache/yum /var/cache/dnf

USER user
