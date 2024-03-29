![Idelium](https://idelium.io/assets/images/idelium.png)

# Idelium-CLI

This is Idelium Command Line is the tool for test automation integrated with [Idelium AS](https://github.com/idelium/idelium-docker).

Idelium-CLI can be used through a continues integration software, such as Jenkins, GitLabs, Bamboo etc.

For more info: https://idelium.io

[![Introducing Idelium](https://img.youtube.com/vi/nGe3c_CU0NQ/0.jpg)](https://youtu.be/nGe3c_CU0NQ)

## Prerequisite

Python 3.8.X

## Installing

If you have pip on your system, you can simply install or upgrade the Python bindings:

```
pip install idelium
```

## Run the command

idelium-cli can be used in two ways:

To directly launch a test cycle, useful for those who want to integrate integration tests with jenkins, bamboo or similar:

```
idelium --ideliumKey=1234 --idCycle=2 --idProject=8 --environment=prod
```

For use with [idelium-docker](https://github.com/idelium/idelium-docker):

```
idelium --ideliumKey=1234 --idCycle=2 --idProject=8 --environment=prod --ideliumwsBaseurl='https://localhost'
```

### idelium-cli server mode
for idelium-cli in server mode useful for those who want to buy idelium enterprise, and then configure different platforms and launch tests remotely:

```
idelium --ideliumServer
```

### options
```
    Usage: idelium [options]

    Options:

    --help                  show this help
    --idCycle               cycle id to associate to the execution "idCycle1,idCycle2,...."
    --idProject             force idProject
    --environment           environment json config file (required)
    --useragent             set useragent for the test
    --test                  for testing without store the results
    --verbose               for debugging 
    --dirChromedriver       default path of chromedriver path ("./chromedriver/last")
    --dirConfigurationStep  default path ("./configurationStep") for configuration steps 
    --dirStepFiles          default path ("./step") of directory for step files 
    --dirIdeliumScript      default path (".") of directory for step files
    --width                 default width of screen 1024
    --height                default height of screen 768
    --device                if is set useragent,height and width are ignored
    --url                   url for test 
    --ideliumwsBaseurl      idelium server url ex: https://localhost
    --reportingService      where the data will be save: idelium | zephyr
    --ideliumKey            is the key for access to the idelium api
    --idChannel             idChannel
    
    Idelium server
    --ideliumServer         with this option idelium-cli is in server mode
    --ideliumServerPort     default is 8691

    Zephir 
    --jiraApiUrl            for change the default jira url (https://<host jira>/rest/api/latest/)
    --idJira                jira id (required if idVersion and idCycle not setted)
    --idVersion             version id to associate the execution 
    --username              jira username (required)
    --password              jira password (required)

```


## Test Libraries used

### Selenium

For configure idelium-cli for test web application with chrome,firefox, windows, safari:

https://www.selenium.dev/documentation/webdriver/

### Appium

For configure idelium-cli for test native, hybrid and mobile web apps with iOS, Android and Windows:

https://appium.io/

## Webdriver

The webdriver is the interface to write instructions that work interchangeably across browsers, each browser has its own driver:

#### ChromeDriver

https://chromedriver.chromium.org/downloads

idelium-cli download automically the correct version

#### Geckodriver for Firefox

https://github.com/mozilla/geckodriver/releases

#### EDGE

https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/

#### Internet Explorer 11

https://support.microsoft.com/en-us/topic/webdriver-support-for-internet-explorer-11-9e1331c5-3198-c835-f622-ada80fe8c1fa

#### Safari

https://developer.apple.com/documentation/webkit/testing_with_webdriver_in_safari

## Thanks

Special thanks to Marco Vernarecci, who supports me to make the product better
