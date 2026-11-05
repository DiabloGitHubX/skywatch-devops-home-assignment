{{/*
Return the chart name, optionally overridden by nameOverride.
*/}}
{{- define "skywatch.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return a release-specific name without duplicating the chart name.
Examples:
  skywatch      -> skywatch
  skywatch-prod -> skywatch-prod
  production    -> production-skywatch
*/}}
{{- define "skywatch.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 55 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "skywatch.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 55 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 55 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Backend resource name.
*/}}
{{- define "skywatch.backend.fullname" -}}
{{- printf "%s-backend" (include "skywatch.fullname" .) -}}
{{- end -}}

{{/*
Frontend resource name.
*/}}
{{- define "skywatch.frontend.fullname" -}}
{{- printf "%s-frontend" (include "skywatch.fullname" .) -}}
{{- end -}}

{{/*
Common labels for all SkyWatch resources.
*/}}
{{- define "skywatch.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/name: {{ include "skywatch.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{/*
Selector labels for a specific component.
*/}}
{{- define "skywatch.selectorLabels" -}}
app.kubernetes.io/name: {{ include "skywatch.name" .root | quote }}
app.kubernetes.io/instance: {{ .root.Release.Name | quote }}
app.kubernetes.io/component: {{ .component | quote }}
{{- end -}}

{{/*
Require exactly seven hexadecimal characters for container image tags.
*/}}
{{- define "skywatch.imageTag" -}}
{{- $tag := required (printf "%s.image.tag must be set to a 7-character Git commit SHA" .component) .tag -}}
{{- if not (regexMatch "^[0-9a-fA-F]{7}$" $tag) -}}
{{- fail (printf "%s.image.tag must contain exactly 7 hexadecimal characters; got %q" .component $tag) -}}
{{- end -}}
{{- $tag -}}
{{- end -}}