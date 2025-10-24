# Terraform example for Hetzner autoscaling with Kubespray API

# Variables
variable "bastion_ip" {
  description = "IP address of the bastion server running the Kubespray scaling API"
  type        = string
  default     = "91.99.14.172"  # Your bastion IP
}

variable "gateway_ip" {
  description = "Gateway IP for the private network"
  type        = string
  default     = "10.10.10.1"
}

variable "worker_count" {
  description = "Number of worker nodes to create"
  type        = number
  default     = 1
}

variable "worker_type" {
  description = "Hetzner server type for workers"
  type        = string
  default     = "cx21"
}

# Data source for the cloud-init template
data "template_file" "worker_cloudinit" {
  template = file("${path.module}/cloudinit-autoscale-simple.yml.tmpl")
  
  vars = {
    bastion_ip = var.bastion_ip
    gateway_ip = var.gateway_ip
  }
}

# Example: Create worker nodes that auto-register with the API
resource "hcloud_server" "worker" {
  count       = var.worker_count
  name        = "worker-${count.index + 4}"  # Starting from worker-4
  image       = "ubuntu-22.04"
  server_type = var.worker_type
  location    = "nbg1"
  
  # Use the simplified cloud-init template
  user_data = data.template_file.worker_cloudinit.rendered
  
  # Add to your private network
  network {
    network_id = hcloud_network.main.id
    ip         = "10.10.10.${count.index + 24}"  # Starting from 10.10.10.24
  }
  
  # Important: Ensure server is created after bastion is ready
  depends_on = [
    hcloud_server.bastion  # Your bastion server resource
  ]
  
  labels = {
    role    = "worker"
    cluster = "mycluster"
  }
}

# Output the worker information
output "worker_nodes" {
  value = [
    for worker in hcloud_server.worker : {
      name       = worker.name
      private_ip = worker.network[0].ip
      public_ip  = worker.ipv4_address
      status_url = "http://${var.bastion_ip}:5000/status?hostname=${worker.name}&ip=${worker.network[0].ip}"
    }
  ]
  description = "Information about created worker nodes"
}

# Example output showing how to check all node statuses
output "check_all_status" {
  value = <<-EOT
    # Check status of all workers:
    %{for worker in hcloud_server.worker~}
    curl "http://${var.bastion_ip}:5000/status?hostname=${worker.name}&ip=${worker.network[0].ip}"
    %{endfor~}
  EOT
  description = "Commands to check registration status"
}

# Optional: Create a data source that waits for nodes to be ready
# This requires the null provider: terraform { required_providers { null = {...} } }
resource "null_resource" "wait_for_registration" {
  count = var.worker_count
  
  triggers = {
    server_id = hcloud_server.worker[count.index].id
  }
  
  provisioner "local-exec" {
    command = <<-EOT
      echo "Waiting for ${hcloud_server.worker[count.index].name} to register..."
      for i in {1..60}; do
        STATUS=$(curl -s "http://${var.bastion_ip}:5000/status?hostname=${hcloud_server.worker[count.index].name}&ip=${hcloud_server.worker[count.index].network[0].ip}" | jq -r '.status' 2>/dev/null || echo "pending")
        echo "Attempt $i: Status = $STATUS"
        
        if [ "$STATUS" = "completed" ]; then
          echo "✓ Node ${hcloud_server.worker[count.index].name} successfully joined!"
          exit 0
        elif [ "$STATUS" = "failed" ]; then
          echo "✗ Node ${hcloud_server.worker[count.index].name} registration failed!"
          exit 1
        fi
        
        sleep 10
      done
      
      echo "Timeout waiting for registration"
      exit 1
    EOT
  }
  
  depends_on = [hcloud_server.worker]
}
