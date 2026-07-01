# Step 0: Install Git
echo -e "\nStep 0: Installing Git..."
yum install git -y
check_status "Git Installation"

# Step 0.1: Verify Git
echo -e "\nStep 0.1: Verifying Git..."
git --version
check_status "Git Verification"

# Step 0.2: Install Maven
echo -e "\nStep 0.2: Installing Maven..."
yum install maven -y
check_status "Maven Installation"

# Step 0.3: Verify Maven
echo -e "\nStep 0.3: Verifying Maven..."
mvn -version >/dev/null 2>&1
check_status "Maven Verification"

# Step 1: Download Jenkins Repository
echo -e "\nStep 1: Downloading Jenkins Repository..."
wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/rpm-stable/jenkins.repo
check_status "Jenkins Repository Download"

# Step 2: Update Packages
echo -e "\nStep 2: Updating System Packages..."
yum upgrade -y
check_status "System Package Upgrade"

# Step 3: Import Corretto Key
echo -e "\nStep 3: Importing Corretto GPG Key..."
rpm --import https://yum.corretto.aws/corretto.key
check_status "Corretto GPG Key Import"

# Step 4: Download Corretto Repository
echo -e "\nStep 4: Downloading Corretto Repository..."
curl -L -o /etc/yum.repos.d/corretto.repo https://yum.corretto.aws/corretto.repo
check_status "Corretto Repository Download"

# Step 5: Install Java
echo -e "\nStep 5: Installing Java 21..."
yum install java-21-openjdk -y
check_status "Java Installation"

# Step 6: Verify Java
echo -e "\nStep 6: Verifying Java..."
java -version
check_status "Java Verification"

# Step 7: Install Fontconfig
echo -e "\nStep 7: Installing Fontconfig..."
yum install fontconfig -y
check_status "Fontconfig Installation"

# Step 8: Install Jenkins
echo -e "\nStep 8: Installing Jenkins..."
yum install jenkins -y
check_status "Jenkins Installation"

# Step 9: Reload Systemd
echo -e "\nStep 9: Reloading Systemd..."
systemctl daemon-reload
check_status "Systemd Reload"

# Step 10: Enable Jenkins Service
echo -e "\nStep 10: Enabling Jenkins..."
systemctl enable jenkins
check_status "Jenkins Enable"

# Step 11: Start Jenkins Service
echo -e "\nStep 11: Starting Jenkins..."
systemctl start jenkins
check_status "Jenkins Start"

# Step 12: Verify Jenkins Service
echo -e "\nStep 12: Verifying Jenkins Service..."
systemctl is-active --quiet jenkins
check_status "Jenkins Running"

# Step 13: Verify Port 8080
echo -e "\nStep 13: Checking Port 8080..."
ss -tulnp | grep 8080 >/dev/null 2>&1
check_status "Jenkins Listening on Port 8080"

# Step 14: Display Jenkins URL
echo -e "\nStep 14: Fetching Server IP..."
SERVER_IP=$(curl -s http://checkip.amazonaws.com)
check_status "Server IP Fetch"

echo "Jenkins URL: http://${SERVER_IP}:8080"

# Step 15: Display Initial Password
echo -e "\nStep 15: Displaying Initial Admin Password..."
cat /var/lib/jenkins/secrets/initialAdminPassword
check_status "Initial Password Display"