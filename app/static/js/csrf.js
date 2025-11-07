/**
 * CSRF Token 管理器
 * 自动处理所有需要CSRF保护的请求
 */

class CSRFManager {
    constructor() {
        this.token = null;
        this.tokenExpiry = null;
        this.refreshing = false;
    }

    /**
     * 获取CSRF token（带缓存）
     */
    async getToken() {
        // 如果token仍然有效，直接返回
        if (this.token && this.tokenExpiry && Date.now() < this.tokenExpiry) {
            return this.token;
        }

        // 如果正在刷新，等待刷新完成
        if (this.refreshing) {
            return new Promise((resolve) => {
                const checkInterval = setInterval(() => {
                    if (!this.refreshing) {
                        clearInterval(checkInterval);
                        resolve(this.token);
                    }
                }, 50);
            });
        }

        // 刷新token
        return await this.refreshToken();
    }

    /**
     * 刷新CSRF token
     */
    async refreshToken() {
        this.refreshing = true;
        try {
            const response = await fetch('/api/csrf-token', {
                method: 'GET',
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to fetch CSRF token');
            }

            const data = await response.json();
            this.token = data.csrf_token;
            // Token缓存10分钟
            this.tokenExpiry = Date.now() + 10 * 60 * 1000;

            return this.token;
        } catch (error) {
            console.error('CSRF token fetch error:', error);
            throw error;
        } finally {
            this.refreshing = false;
        }
    }

    /**
     * 清除token缓存
     */
    clearToken() {
        this.token = null;
        this.tokenExpiry = null;
    }
}

// 创建全局实例
window.csrfManager = new CSRFManager();

/**
 * 配置Axios自动添加CSRF token
 */
if (typeof axios !== 'undefined') {
    // 请求拦截器：自动添加CSRF token
    axios.interceptors.request.use(
        async (config) => {
            // 仅对需要CSRF保护的方法添加token
            const protectedMethods = ['post', 'put', 'patch', 'delete'];
            if (protectedMethods.includes(config.method.toLowerCase())) {
                try {
                    const token = await window.csrfManager.getToken();
                    config.headers['X-CSRFToken'] = token;
                } catch (error) {
                    console.error('Failed to add CSRF token:', error);
                }
            }

            // 确保携带credentials
            if (config.withCredentials === undefined) {
                config.withCredentials = true;
            }

            return config;
        },
        (error) => {
            return Promise.reject(error);
        }
    );

    // 响应拦截器：处理CSRF错误和未登录
    axios.interceptors.response.use(
        (response) => response,
        async (error) => {
            const originalRequest = error.config;

            // 处理401未登录错误
            if (error.response && error.response.status === 401) {
                // 排除登录接口本身的401错误（密码错误）和注册接口
                const isLoginRequest = originalRequest.url && originalRequest.url.includes('/api/login');
                const isRegisterRequest = originalRequest.url && originalRequest.url.includes('/api/register');
                const isPublicPage = window.location.pathname === '/login' || window.location.pathname === '/register';

                // 如果是登录/注册请求失败，或者已经在登录/注册页面，不要跳转
                if (!isLoginRequest && !isRegisterRequest && !isPublicPage) {
                    console.warn('检测到401未登录，跳转到登录页...');
                    // 保存当前URL，登录后可以跳回
                    const returnUrl = encodeURIComponent(window.location.pathname + window.location.search);
                    window.location.href = `/login?return=${returnUrl}`;
                }
                return Promise.reject(error);
            }

            // 如果是CSRF错误且未重试过
            if (error.response && error.response.status === 400 && !originalRequest._retry) {
                const errorMsg = error.response.data?.error || '';
                if (errorMsg.toLowerCase().includes('csrf')) {
                    originalRequest._retry = true;

                    try {
                        // 刷新token并重试
                        const token = await window.csrfManager.refreshToken();
                        originalRequest.headers['X-CSRFToken'] = token;
                        return axios(originalRequest);
                    } catch (refreshError) {
                        console.error('CSRF token refresh failed:', refreshError);
                    }
                }
            }

            return Promise.reject(error);
        }
    );

    // 设置默认配置
    axios.defaults.withCredentials = true;
}

/**
 * 包装fetch以自动添加CSRF token
 */
const originalFetch = window.fetch;
window.fetch = async function(url, options = {}) {
    const method = (options.method || 'GET').toLowerCase();
    const protectedMethods = ['post', 'put', 'patch', 'delete'];

    // 如果是需要保护的方法，添加CSRF token
    if (protectedMethods.includes(method)) {
        try {
            const token = await window.csrfManager.getToken();

            options.headers = options.headers || {};
            if (!options.headers['X-CSRFToken']) {
                options.headers['X-CSRFToken'] = token;
            }
        } catch (error) {
            console.error('Failed to add CSRF token to fetch:', error);
        }
    }

    // 确保携带credentials
    if (!options.credentials) {
        options.credentials = 'include';
    }

    return originalFetch(url, options);
};

/**
 * 工具函数：手动获取CSRF token
 */
window.getCSRFToken = async function() {
    return await window.csrfManager.getToken();
};

/**
 * 工具函数：清除CSRF token缓存（用于登出时）
 */
window.clearCSRFToken = function() {
    window.csrfManager.clearToken();
};

// 页面加载时预加载token
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.csrfManager.getToken().catch(err => {
            console.warn('Failed to preload CSRF token:', err);
        });
    });
} else {
    window.csrfManager.getToken().catch(err => {
        console.warn('Failed to preload CSRF token:', err);
    });
}

console.log('✓ CSRF protection initialized');
