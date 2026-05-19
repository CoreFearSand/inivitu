/**
 * Configuration Management JavaScript
 * Handles the configuration interface functionality
 */

class ConfigManager {
    constructor() {
        this.originalConfig = {};
        this.currentConfig = {};
        this.isLoading = false;
        
        this.init();
    }
    
    init() {
        this.storeOriginalConfig();

        this.bindEvents();

        this.loadCurrentConfig();
    }
    
    storeOriginalConfig() {
        const form = document.getElementById('config-form');
        if (!form) return;
        
        const formData = new FormData(form);
        this.originalConfig = {};
        
        for (let [key, value] of formData.entries()) {
            if (key === 'enable_websocket' || key === 'enable_map_features') {
                this.originalConfig[key] = document.getElementById(key).checked;
            } else if (key === 'web_port' || key === 'polling_interval' || 
                       key === 'max_file_size_mb' || key === 'processing_timeout_seconds' || 
                       key === 'default_country_count') {
                this.originalConfig[key] = parseFloat(value);
            } else {
                this.originalConfig[key] = value;
            }
        }
        
        this.currentConfig = { ...this.originalConfig };
    }
    
    bindEvents() {
        const form = document.getElementById('config-form');
        if (form) {
            form.addEventListener('submit', (e) => this.handleSubmit(e));
        }

        const resetBtn = document.getElementById('reset-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetForm());
        }

        const validateBtn = document.getElementById('validate-btn');
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.validateConfiguration());
        }

        const dirValidateBtn = document.getElementById('validate-dir-btn');
        if (dirValidateBtn) {
            dirValidateBtn.addEventListener('click', () => this.validateDirectory());
        }

        window.addEventListener('beforeunload', (e) => this.handleBeforeUnload(e));

        const inputs = form.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('change', () => this.detectChanges());
        });
    }
    
    async loadCurrentConfig() {
        try {
            const response = await fetch('/api/config');
            const result = await response.json();
            
            if (response.ok && result.config) {
                this.currentConfig = result.config;
                this.updateFormFromConfig(result.config);
            }
        } catch (error) {
            console.error('Failed to load current config:', error);
            this.showAlert('Failed to load current configuration', 'warning');
        }
    }
    
    updateFormFromConfig(config) {
        for (const [key, value] of Object.entries(config)) {
            const element = document.getElementById(key);
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = value;
                } else {
                    element.value = value;
                }
            }
        }
    }
    
    getFormData() {
        const form = document.getElementById('config-form');
        const formData = new FormData(form);
        const config = {};
        
        for (let [key, value] of formData.entries()) {
            if (key === 'enable_websocket' || key === 'enable_map_features') {
                config[key] = document.getElementById(key).checked;
            } else if (key === 'web_port' || key === 'polling_interval' || 
                       key === 'max_file_size_mb' || key === 'processing_timeout_seconds' || 
                       key === 'default_country_count') {
                config[key] = parseFloat(value);
            } else {
                config[key] = value;
            }
        }
        
        return config;
    }
    
    detectChanges() {
        const currentFormData = this.getFormData();
        const hasChanges = JSON.stringify(currentFormData) !== JSON.stringify(this.originalConfig);

        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) {
            if (hasChanges) {
                submitBtn.classList.add('btn-warning');
                submitBtn.classList.remove('btn-primary');
                submitBtn.querySelector('.btn-text').textContent = 'Save Changes';
            } else {
                submitBtn.classList.add('btn-primary');
                submitBtn.classList.remove('btn-warning');
                submitBtn.querySelector('.btn-text').textContent = 'Save Configuration';
            }
        }
    }
    
    showAlert(message, type = 'info') {
        const container = document.getElementById('alert-container');
        if (!container) return;
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `
            <span>${message}</span>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        container.appendChild(alert);

        setTimeout(() => {
            if (alert.parentElement) {
                alert.remove();
            }
        }, 5000);
    }
    
    setLoading(loading) {
        this.isLoading = loading;
        
        const loadingSpan = document.querySelector('.loading');
        const btnText = document.querySelector('.btn-text');
        const submitBtn = document.querySelector('button[type="submit"]');
        
        if (loading) {
            if (loadingSpan) loadingSpan.style.display = 'inline';
            if (btnText) btnText.style.display = 'none';
            if (submitBtn) submitBtn.disabled = true;
        } else {
            if (loadingSpan) loadingSpan.style.display = 'none';
            if (btnText) btnText.style.display = 'inline';
            if (submitBtn) submitBtn.disabled = false;
        }
    }
    
    async validateDirectory() {
        const saveDir = document.getElementById('save_directory').value;
        
        if (!saveDir.trim()) {
            this.showAlert('Please enter a save directory path', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/config/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ save_directory: saveDir })
            });
            
            const result = await response.json();
            
            if (result.save_directory_valid) {
                this.showAlert('✅ Save directory is valid and accessible', 'success');
            } else if (result.errors && result.errors.length > 0) {
                this.showAlert(`❌ ${result.errors[0]}`, 'danger');
            } else {
                this.showAlert('❌ Save directory validation failed', 'danger');
            }
        } catch (error) {
            console.error('Validation error:', error);
            this.showAlert('Failed to validate directory', 'danger');
        }
    }
    
    async validateConfiguration() {
        const config = this.getFormData();
        
        try {
            const response = await fetch('/api/config/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(config)
            });
            
            const result = await response.json();
            
            if (result.valid) {
                this.showAlert('✅ Configuration is valid', 'success');
            } else {
                const errors = result.errors || ['Configuration validation failed'];
                this.showAlert(`❌ Validation errors: ${errors.join(', ')}`, 'danger');
            }
        } catch (error) {
            console.error('Validation error:', error);
            this.showAlert('Failed to validate configuration', 'danger');
        }
    }
    
    resetForm() {
        const form = document.getElementById('config-form');
        if (!form) return;
        
        // Reset all form fields to original values
        for (const [key, value] of Object.entries(this.originalConfig)) {
            const element = document.getElementById(key);
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = value;
                } else {
                    element.value = value;
                }
            }
        }
        
        this.detectChanges();
        this.showAlert('Form reset to current configuration', 'info');
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        if (this.isLoading) return;
        
        this.setLoading(true);
        
        try {
            const config = this.getFormData();
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(config)
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                this.showAlert('✅ Configuration saved successfully!', 'success');

                this.originalConfig = { ...config };
                this.currentConfig = { ...config };
                this.detectChanges();

                if (config.web_port !== this.currentConfig.web_port) {
                    this.showAlert('⚠️ Web port changed. Please restart the application for changes to take effect.', 'warning');
                }
            } else {
                this.showAlert(`❌ Failed to save configuration: ${result.error || 'Unknown error'}`, 'danger');
            }
        } catch (error) {
            console.error('Save error:', error);
            this.showAlert('❌ Failed to save configuration', 'danger');
        } finally {
            this.setLoading(false);
        }
    }
    
    handleBeforeUnload(e) {
        const currentFormData = this.getFormData();
        const hasChanges = JSON.stringify(currentFormData) !== JSON.stringify(this.originalConfig);
        
        if (hasChanges && !this.isLoading) {
            e.preventDefault();
            e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            return e.returnValue;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('config-form')) {
        window.configManager = new ConfigManager();
    }
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ConfigManager;
}