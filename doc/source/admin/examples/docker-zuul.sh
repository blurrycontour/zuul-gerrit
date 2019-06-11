#!/usr/bin/env sh

# start the compose
docker-compose up -d

GERRITCONTAINER=$(docker-compose ps | grep _gerrit_ | awk '{print $1}')
GERRITCONFCONTAINER=$(docker-compose ps | grep _gerritconfig_ | awk '{print $1}')

echo "Wait for initial gerrit provisioning ..."
docker wait $GERRITCONFCONTAINER

# Reconfigure Gerrit
docker exec -it $GERRITCONTAINER git config -f /var/gerrit/review_site/etc/gerrit.config auth.type "OAUTH"
docker exec -it $GERRITCONTAINER git config -f /var/gerrit/review_site/etc/gerrit.config plugin.gerrit-oauth-provider-keycloak-oauth.client-id "gerrit-client"
docker exec -it $GERRITCONTAINER git config -f /var/gerrit/review_site/etc/gerrit.config plugin.gerrit-oauth-provider-keycloak-oauth.client-secret "868e895b-73a7-4459-9347-cd85c05e9bd7"
docker exec -it $GERRITCONTAINER git config -f /var/gerrit/review_site/etc/gerrit.config plugin.gerrit-oauth-provider-keycloak-oauth.realm "zuul-demo"
docker exec -it $GERRITCONTAINER git config -f /var/gerrit/review_site/etc/gerrit.config plugin.gerrit-oauth-provider-keycloak-oauth.root-url "http://localhost:8282"

# Restart Gerrit
docker exec -it $GERRITCONTAINER su-exec gerrit2 cp -f /var/gerrit/oauth.jar /var/gerrit/review_site/plugins/oauth.jar
docker exec -it $GERRITCONTAINER su-exec gerrit2 /var/gerrit/review_site/bin/gerrit.sh stop
docker exec -it $GERRITCONTAINER su-exec gerrit2 /var/gerrit/review_site/bin/gerrit.sh daemon

# show logs
docker-compose logs -f
