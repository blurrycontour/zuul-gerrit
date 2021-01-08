#!/bin/bash -e

export JAVA_OPTS='--add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/java.lang.invoke=ALL-UNNAMED'

if [ ! -d /var/gerrit/git/All-Projects.git ] || [ "$1" == "init" ]
then
  echo "Initializing Gerrit site ..."
  java $JAVA_OPTS -jar /var/gerrit/bin/gerrit.war init --batch --install-all-plugins -d /var/gerrit
  java $JAVA_OPTS -jar /var/gerrit/bin/gerrit.war reindex -d /var/gerrit
  git config -f /var/gerrit/etc/gerrit.config --add container.javaOptions "-Djava.security.egd=file:/dev/./urandom"
  git config -f /var/gerrit/etc/gerrit.config --add container.javaOptions "--add-opens java.base/java.net=ALL-UNNAMED"
  git config -f /var/gerrit/etc/gerrit.config --add container.javaOptions "--add-opens java.base/java.lang.invoke=ALL-UNNAMED"
  # Disable email notifications
  git config -f /var/gerrit/etc/gerrit.config --add sendemail.enable "false"
  echo "Configuring auth ..."
  git config -f /var/gerrit/etc/gerrit.config auth.type "OAUTH"
  git config -f /var/gerrit/etc/gerrit.config --add plugin.gerrit-oauth-provider-keycloak-oauth.client-id "gerrit"
  git config -f /var/gerrit/etc/gerrit.config --add plugin.gerrit-oauth-provider-keycloak-oauth.client-secret "86909744-7109-4cbe-8044-fb1de3be6acd"
  git config -f /var/gerrit/etc/gerrit.config --add plugin.gerrit-oauth-provider-keycloak-oauth.realm "zuul-demo"
  git config -f /var/gerrit/etc/gerrit.config --add plugin.gerrit-oauth-provider-keycloak-oauth.root-url "http://keycloak:8082"
  # git config -f /var/gerrit/etc/gerrit.config --unset httpd.filterClass
  # git config -f /var/gerrit/etc/gerrit.config --unset httpd.firstTimeRedirectUrl

fi

git config -f /var/gerrit/etc/gerrit.config gerrit.canonicalWebUrl "${CANONICAL_WEB_URL:-http://$HOSTNAME}"
if [ ${HTTPD_LISTEN_URL} ];
then
  git config -f /var/gerrit/etc/gerrit.config httpd.listenUrl ${HTTPD_LISTEN_URL}
fi

if [ "$1" != "init" ]
then
  echo "Pre-provision admin user ..."
  /usr/local/bin/pynotedb create-admin-user --email "admin@example.com" --pubkey "$(cat /gerrit_admin_key.pub)" --all-users /var/gerrit/git/All-Users.git --scheme keycloak-oauth
  echo "Running Gerrit ..."
  exec /var/gerrit/bin/gerrit.sh run
fi
