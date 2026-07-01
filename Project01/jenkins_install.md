sudo wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/rpm-stable/jenkins.repo
sudo yum upgrade -y
# Add required dependencies for the jenkins package
rpm --import https://yum.corretto.aws/corretto.key 
curl -L -o /etc/yum.repos.d/corretto.repo https://yum.corretto.aws/corretto.repo
sudo yum install java-21-openjdk -y
sudo yum install fontconfig -y
sudo yum install jenkins -y 
sudo systemctl daemon-reload
sudo systemctl start jenkins