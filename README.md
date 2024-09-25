# BLUM AUTO

BLUM Telegram Mini App Bot

For README in Bahasa Indonesia: [![en](https://img.shields.io/badge/README-id-red.svg)](https://github.com/dzuhri-auto/blum-query-id/blob/master/README.id.md)

## Feature

- Auto Claim Daily Check-in
- Auto Farming
- Auto Claim Friend Ref
- Auto Clear Mission / Tasks
- Auto Play Game

## .env Settings

| Name                    | Description                                     | Default    |
| ----------------------- | ----------------------------------------------- | ---------- |
| API_KEY                 | Custom API KEY                                  |            |
| PLAY_GAMES              | Auto Play Game                                  | True       |
| POINTS                  | Randomize score for each game                   | [200, 300] |
| USE_REF                 | Use refferall code                              | False      |
| REF_ID                  | Referral code                                   | ""         |
| USE_RANDOM_DELAY_IN_RUN | Activate delay before start the bot             | True       |
| RANDOM_DELAY_IN_RUN     | Randomize delay in seconds before start the bot | [5, 30]    |
| USE_PROXY_FROM_FILE     | For using proxy                                 | False      |

## Prerequisites

Make sure you already install:

- [Python](https://www.python.org/downloads/release/python-31014/) **version 3.10**

## How to obtain Query ID

<https://irhamdz.notion.site/Tutorial-Get-Query-ID-f415621d4a9843d2a7a9ad2cfb9abeb4?pvs=74>

## Request API KEY

This script use custom API KEY, The API KEY itself is for rent only

you can chat me, [Irham](https://t.me/irhamdz) to ask how much the rent price !

## Install

Clone to your PC / VPS:

```shell
git clone https://github.com/dzuhri-auto/blum-query-id.git
```

Go inside to the folder:

```shell
cd blum-query-id
```

Then use this command for automatic install:

**Windows** :

```shell
windows\install.bat
```

**Mac / Linux / VPS** :

```shell
sudo chmod +x ubuntu/install.sh ubuntu/run.sh
```

```shell
source ./ubuntu/install.sh
```

***note : dont forget to edit file `.env`***

## Update API KEY

After install we can update using API KEY:

**Windows** :

```shell
$filePath = ".env"
$searchPattern = "^API_KEY="
$replacement = 'API_KEY="YOUR API KEY"'

(Get-Content $filePath) -replace $searchPattern + '.*', $replacement | Set-Content $filePath
```

**Mac / Linux / VPS** :

```shell
sed -i~ '/^API_KEY=/s/=.*/="YOUR API KEY"/' .env

# example if your API KEY = "aisjiqiqssq"
# sed -i~ '/^API_KEY=/s/=.*/="aisjiqiqssq"/' .env
```

## Start Bot

For run the bot:

**Windows** :

```shell
windows\run.bat
```

**Mac / Linux / VPS** :

```shell
./ubuntu/run.sh
```
