import os
import re

mapping = {
    r'\bbg-gray-900/20\b': 'bg-background-20',
    r'\bbg-gray-900\b': 'bg-background',
    
    r'\bbg-gray-800/50\b': 'bg-surface-50',
    r'\bbg-gray-800/80\b': 'bg-surface-80',
    r'\bbg-gray-800\b': 'bg-surface',
    
    r'\bbg-gray-700\b': 'bg-surface-elevated',
    
    r'\bbg-black/80\b': 'bg-black-base-80',
    r'\bbg-black\b': 'bg-black-base',
    r'\bbg-white\b': 'bg-white-base',
    
    r'\btext-white\b': 'text-text-primary',
    r'\btext-gray-300\b': 'text-text-secondary',
    r'\btext-gray-400\b': 'text-text-muted',
    r'\btext-gray-500\b': 'text-text-disabled',
    r'\btext-black\b': 'text-text-inverse',
    
    r'\bborder-gray-900\b': 'border-border-dark',
    r'\bborder-gray-800/50\b': 'border-border-subtle-50',
    r'\bborder-gray-800\b': 'border-border-subtle',
    r'\bborder-gray-700\b': 'border-border-strong',
    r'\bborder-gray-600\b': 'border-border-highlight',
    
    r'\bbg-green-400\b': 'bg-accent-light',
    r'\bbg-green-500\b': 'bg-accent',
    r'\bbg-green-600/20\b': 'bg-accent-dark-20',
    r'\bbg-green-600/40\b': 'bg-accent-dark-40',
    r'\bbg-green-600\b': 'bg-accent-dark',
    r'\btext-green-400\b': 'text-accent-light',
    r'\btext-green-500\b': 'text-accent',
    r'\bborder-green-500\b': 'border-accent',
    r'\bborder-green-600/50\b': 'border-accent-dark-50',
    r'\bhover:bg-green-400\b': 'hover:bg-accent-light',
    r'\bhover:bg-green-500\b': 'hover:bg-accent',
    r'\bhover:text-green-400\b': 'hover:text-accent-light',
    r'\bhover:text-green-500\b': 'hover:text-accent',
    r'\bhover:border-green-500\b': 'hover:border-accent',
    r'\bfocus:ring-green-500\b': 'focus:ring-accent',
    r'\bfocus:border-green-500\b': 'focus:border-accent',
    r'\baccent-green-500\b': 'accent-accent',
    r'\bhover:accent-green-500\b': 'hover:accent-accent',
    
    r'\bbg-red-400\b': 'bg-danger-light',
    r'\bbg-red-500\b': 'bg-danger',
    r'\bbg-red-600\b': 'bg-danger-dark',
    r'\bbg-red-900/20\b': 'bg-danger-darkest-20',
    r'\btext-red-400\b': 'text-danger-light',
    r'\btext-red-500\b': 'text-danger',
    r'\bborder-red-500/30\b': 'border-danger-30',
    r'\bborder-red-500\b': 'border-danger',
    r'\bhover:bg-red-400\b': 'hover:bg-danger-light',
    r'\bhover:bg-red-500\b': 'hover:bg-danger',
    r'\bhover:text-red-400\b': 'hover:text-danger-light',
    
    r'\bbg-blue-400\b': 'bg-info-light',
    r'\bbg-blue-500/20\b': 'bg-info-20',
    r'\bbg-blue-500\b': 'bg-info',
    r'\bbg-blue-600/20\b': 'bg-info-dark-20',
    r'\bbg-blue-600/40\b': 'bg-info-dark-40',
    r'\bbg-blue-600\b': 'bg-info-dark',
    r'\btext-blue-400\b': 'text-info-light',
    r'\btext-blue-500\b': 'text-info',
    r'\bborder-blue-500/30\b': 'border-info-30',
    r'\bborder-blue-600/50\b': 'border-info-dark-50',
    r'\bhover:bg-blue-400\b': 'hover:bg-info-light',
    r'\bhover:bg-blue-500\b': 'hover:bg-info',
    r'\bhover:bg-blue-600/40\b': 'hover:bg-info-dark-40',
    
    r'\bbg-yellow-500/20\b': 'bg-warning-20',
    r'\bbg-yellow-500\b': 'bg-warning',
    r'\bbg-yellow-600/20\b': 'bg-warning-dark-20',
    r'\bbg-yellow-600/40\b': 'bg-warning-dark-40',
    r'\bbg-yellow-600\b': 'bg-warning-dark',
    r'\btext-yellow-500\b': 'text-warning',
    r'\bborder-yellow-500/30\b': 'border-warning-30',
    r'\bborder-yellow-600/50\b': 'border-warning-dark-50',
    r'\bhover:bg-yellow-500\b': 'hover:bg-warning',
    r'\bhover:bg-yellow-600/40\b': 'hover:bg-warning-dark-40',
}

vue_files = [
    'frontend/src/App.vue',
    'frontend/src/components/PlaylistsDashboard.vue',
    'frontend/src/components/PlaylistDetail.vue',
    'frontend/src/components/WebPlayer.vue'
]

for filepath in vue_files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for k, v in mapping.items():
        content = re.sub(k, v, content)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

