dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm
dnf -qy module disable postgresql
dnf install -y epel-release
dnf config-manager --enable ol8_codeready_builder
dnf install -y postgresql15-server-15.8
dnf install -y postgresql15-contrib-15.8
dnf install -y postgresql15-devel-15.8
dnf install -y openssh-server openssh-clients rsync
dnf install -y make gcc redhat-rpm-config openssl-devel clang llvm
/usr/pgsql-15/bin/postgresql-15-setup initdb
echo 'host    all             all             0.0.0.0/0               md5' >> /var/lib/pgsql/15/data/pg_hba.conf
echo 'host    replication     all             0.0.0.0/0               md5' >> /var/lib/pgsql/15/data/pg_hba.conf
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/g" /var/lib/pgsql/15/data/postgresql.conf
systemctl start postgresql-15
runuser -l postgres -c "psql -c \"create user root with password 'root' SUPERUSER;\""
runuser -l postgres -c 'createdb --owner=root root'
