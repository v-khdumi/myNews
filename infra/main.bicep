targetScope = 'resourceGroup'

@description('Globally unique Web App name.')
param appName string

param location string = resourceGroup().location

@description('App Service plan SKU. B1 incurs Azure charges.')
param sku string = 'B1'

@description('Azure OpenAI/Foundry resource endpoint, not the project URL. Leave empty to run RSS only.')
param aiEndpoint string = ''

param aiDeployment string = ''

@description('API key or an App Service Key Vault reference. Never put a literal key in source control.')
@secure()
param aiApiKey string = ''

@minValue(0)
@maxValue(200)
param aiMaxArticlesPerRun int = 20

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${appName}-plan'
  location: location
  sku: {
    name: sku
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource web 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'gunicorn --config gunicorn.conf.py server:app'
      alwaysOn: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'NEWS_DATA_PATH', value: '/home/mynews/news.json' }
        { name: 'NEWS_UPDATE_MINUTES', value: '15' }
        { name: 'NEWS_AUTO_UPDATE', value: '1' }
        { name: 'AI_MAX_ARTICLES_PER_RUN', value: string(aiMaxArticlesPerRun) }
        { name: 'AZURE_OPENAI_ENDPOINT', value: aiEndpoint }
        { name: 'AZURE_OPENAI_DEPLOYMENT', value: aiDeployment }
        { name: 'AZURE_OPENAI_API_KEY', value: aiApiKey }
      ]
    }
  }
}

resource sourceControl 'Microsoft.Web/sites/sourcecontrols@2023-12-01' = {
  parent: web
  name: 'web'
  properties: {
    repoUrl: 'https://github.com/v-khdumi/myNews'
    branch: 'main'
    isManualIntegration: true
  }
}

output url string = 'https://${web.properties.defaultHostName}'
output principalId string = web.identity.principalId
