# BLUM AUTO

BLUM Telegram Mini App Bot

For README in English: [![en](https://img.shields.io/badge/README-en-red.svg)](https://github.com/dzuhri-auto/blum-query-id/blob/master/README.md)

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

## Persiapan

Pastikan kamu sudah menginstal:

- [Python](https://www.python.org/downloads/release/python-31014/) **versi 3.10**

## Mendapatkan Query ID

<https://irhamdz.notion.site/Tutorial-Get-Query-ID-f415621d4a9843d2a7a9ad2cfb9abeb4?pvs=74>

## Mendapatkan API KEY

Script ini menggunakan kustom API KEY, API KEY nya hanya tersedia untuk disewa.

Kamu bisa chat saya, [Irham](https://t.me/irhamdz) untuk menanyakan harga sewanya!

## Install

Clone ke PC / VPS kamu:

```shell
git clone https://github.com/dzuhri-auto/blum-query-id.git
```

Masuk ke folder:

```shell
cd blum-query-id
```

Kemudian gunakan perintah ini untuk instal otomatis:

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

***note : Jangan lupa untuk mengedit file `.env`***

## Update API KEY

Setelah instalasi, kita bisa memperbarui menggunakan API KEY:

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

# contoh jika API KEY kamu = "aisjiqiqssq"
# sed -i~ '/^API_KEY=/s/=.*/="aisjiqiqssq"/' .env
```

## Menjalankan Bot

Untuk menjalankan bot:

**Windows** :

```shell
windows\run.bat
```

**Mac / Linux / VPS** :

```shell
./ubuntu/run.sh
```
