{{/*
Expand the name of the chart.
*/}}
{{- define "ns-api-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ns-api-gateway.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "ns-api-gateway.labels" -}}
helm.sh/chart: {{ include "ns-api-gateway.name" . }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "ns-api-gateway.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "ns-api-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ns-api-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
