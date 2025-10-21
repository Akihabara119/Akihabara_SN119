# Akihabara  Miner Setup Guide
This guide will walk you through the process of deploying and running a Akihabara  miner node, enabling you to connect your local computing power to the Bittensor network and support validators in decentralized AI task processing.

* [Overview](#overview)
* [Prerequisites](#prerequisites)
* [Setup Steps](#setup-steps)
    * [1. Bittensor Wallet Setup](#1-bittensor-wallet-setup)
    * [2. Install Redis](#2-install-redis)
    * [3. Install Akihabara](#3-install-Akihabara)
    * [4. Configuration](#4-configuration)
    * [5. Running the miner](#5-running-the-miner)
    * [Important Parameters](#important-parameters)
* [Mining and resource allocation details](#mining-and-resource-allocation-details)
* [Mining Window and Slots](#mining-window-and-slots)
* [Allocation Strategies](#allocation-strategies)
    * [Stake based allocation (Time splitting)](#stake-based-allocation-time-splitting)
    * [Equal distribution (Time splitting)](#equal-distribution-time-splitting)
* [Ending notes](#ending-notes)



## Overview
The Akihabara  miner intelligently allocates local computing power to validators based on on-chain stake weights, efficiently coordinating model processing tasks within the Bittensor network. The system is composed of the following core components:

## Prerequisites
1. A Bittensor wallet
2. Bittensor mining hardware ( GPUs, etc.)
3. Redis server for data persistence
4. Python 3.10 or higher

## Setup Steps
## 1. Bittensor Wallet Setup

Ensure you have created a Bittensor wallet. If you haven't, you can create one using:
```bash
pip install bittensor-cli
btcli wallet create
btcli subnet register --netuid 119 --wallet.name YOUR_WALLET --wallet.hotkey YOUR_HOTKEY --network finney
```
You can use the network `test` when testing on testnet. 

## 2. Install Redis

### Ubuntu/Debian
```bash
sudo apt update && sudo apt install redis-server -y
sudo systemctl enable redis-server
sudo systemctl start redis-server
```
### MacOS
```bash
brew install redis
brew services start redis
```
### Verify installation
```bash
redis-cli ping
```
You should receive PONG as a response.

## 3. Install Akihabara

```bash
# Clone repository
git clone https://github.com/Akihabara119/Akihabara_SN119.git
cd akihabara

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .
```
## 4. Configuration

You can configure the miner using either a .env file (recommended) or command-line arguments.

### Option 1: Using .env File (Recommended)
1. Create a `.env.miner` file in the project root based on the provided example:
```bash
cd akihabara/miner
cp .env.miner.example .env.miner
```

2. Edit the `.env.miner` file with your credentials:
```bash
nano .env.miner
cd ../.. # Return to the root dir
```
3. Create a `.env.multimodal_server` 
```bash
cd multimodal_server
cp .multimodal_server.example .env.multimodal_server
```
### Option 2: Using Command-Line Arguments

All settings can be passed as command-line arguments when starting the miner.

## 5.Download models
```bash
cd multimodal_server
export HF_TOKEN="hf token here"

in your ComfyUI/models/text_encoders/ directory 
 
wget -c --header="Authorization: Bearer $HF_TOKEN" \
     -O t5xxl_fp16.safetensors \
     "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors?download=true"
     
wget -c --header="Authorization: Bearer $HF_TOKEN" \
     -O clip_l.safetensors \
     "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors?download=true"

Put the flux1-dev.safetensors file in your: ComfyUI/models/diffusion_models/ folder.

wget -c --header="Authorization: Bearer $HF_TOKEN" \
     -O flux1-dev.safetensors \
     "https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors?download=true"
     
in your ComfyUI/models/vae/ directory 

wget -c --header="Authorization: Bearer $HF_TOKEN" \
     -O ae.safetensors \
     "https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors?download=true"

```

## 6. Running the miner

PM2 provides process management with automatic restarts:

1. Install PM2
```bash
sudo apt update && sudo apt install nodejs npm -y
sudo npm install pm2@latest -g
pm2 startup
```

2. Start the miner
```bash
# Using .env file
pm2 start python3 --name "Akihabara-miner" -- akihabara/miner/miner_server.py run \
    --subtensor.network finney \
    --logging.info
    
pm2 start python3 --name "Akihabara-multimodal_server" -- multimodal_server/main.py run \
    --subtensor.network finney \
    --logging.info

# Using command-line arguments
pm2 start python3 --name "Akihabara-miner" -- akihabara/miner/miner_server.py run \
    --netuid 119 \
    --subtensor.network finney \
    --wallet.name YOUR_WALLET_NAME \
    --wallet.hotkey YOUR_HOTKEY \
    --storage_type redis \
    --logging.info

# Or without PM2
python3 akihabara/miner/miner_server.py run \
    --netuid 119 \
    --subtensor.network finney \
    --wallet.name YOUR_WALLET_NAME \
    --wallet.hotkey YOUR_HOTKEY \
    --storage_type redis \
    --logging.info
```
3. Save PM2 config 
```bash
pm2 save
```

## Important Parameters
- `netuid`: Set to 119 for Akihabara  subnet
- `subtensor.network`: Set to `finney` for mainnet
- `wallet.name`: Your Bittensor wallet name
- `wallet.hotkey`: Your wallet's hotkey
- `storage_type`: Storage backend (redis recommended)
---

# Mining and resource allocation details


## Incentive

In Akihabara , miners earn rewards by contributing hashrate to multiple validators. To maximize their returns, miners must dynamically balance their hashrate allocation and strategically respond to Alpha reward emissions.

### Goal
Allocate your hashrate to each validator proportionally to their on-chain stake weight.

## Miner components

### - Bittensor Wallet: 
Manages cryptographic keys and identity for subnet registration and Bittensor operations. 

### - Miner file
Core orchestration component responsible for validator selection, hashrate allocation, and managing AI task processing for validators.

### - Storage
Persistent data layer (Redis) that stores  configurations, schedules, and AI task state between restarts.

---

## Allocation Strategies

We define basic allocation strategies for miners to split their hash-rate based on window-based scheduling.
These strategies are a base-line and sort of a reference; miners are incentived come up with optimal and refined algorithms for most efficient splitting. 

### Stake based allocation (Time splitting)

This default strategy distributes mining blocks proportionally based on stake weight. It's a greedy approach that prioritizes validators with higher stake:
1. Fair Share Calculation: Each validator receives blocks based on their relative stake in the network (stake_validator / total_stake)
2. Minimum Guarantee: Ensures each validator receives at least min_blocks_per_miner (default: 40)
3. Priority Order: Processes miners in descending stake order
4. Efficient Usage: Any remaining blocks are added to the last miner's allocation

This strategy balances reward maximization (by favoring high-stake validators) while ensuring minimum coverage requirements are met for smaller stakeholders.

### Equal distribution (Time splitting)

This strategy implements an egalitarian approach that ignores stake weights:
1. Even Division: Divides available blocks equally among all eligible validators
2. Remainder Handling: Distributes any leftover blocks (one each) to the first N validators
3. Minimum Guarantee: Still ensures each validator receives at least min_blocks_per_validator

## Ending notes

- Miners can connect their own setup or write their own proxy instance to control their miners whatever way they see fit. 

- By default, the miner stores pool informations (with defined TTLs) and the latest schedule in the storage. This was deliberate as to provide flexibility for individuals to consume it as they see fit or permanently store in persistent storage for analytics. 

- Each allocation strategy have different parameters through which it can be controlled. Feel free to read them and tweak/update as needed for your use-case. 

- Validators complete the evaluation of miner work output after 1 full window (2 * tempo). They poll the proxy pools every 5 minutes (25 blocks) to fetch miner contributions. 

- We welcome open-source collaborations! You can find more information about contributions in our github. 

- We will be expanding to support other coins and pools in the future. 

- To run on different environments, check out [Subnet tutorials](https://docs.bittensor.com/tutorials/basic-subnet-tutorials)
