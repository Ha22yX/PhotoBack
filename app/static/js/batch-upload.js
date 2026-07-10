/**
 * 分批上传功能
 * 每次只上传一张照片并显示进度
 */
// 检查是否已经定义了BatchUploader类
if (typeof window.BatchUploader === 'undefined') {
    window.BatchUploader = class {
        constructor(options) {
            this.files = []; // 待上传的文件列表
            this.uploadUrl = options.uploadUrl; // 上传地址
            this.maxRetries = options.maxRetries || 3; // 最大重试次数
            this.currentIndex = 0; // 当前上传的文件索引
            this.totalFiles = 0; // 文件总数
            this.uploadedFiles = 0; // 已上传的文件数
            this.onProgress = options.onProgress || function(){}; // 进度回调
            this.onComplete = options.onComplete || function(){}; // 完成回调
            this.onError = options.onError || function(){}; // 错误回调
            this.csrfToken = options.csrfToken || ''; // CSRF令牌
            this.compressImages = options.compressImages !== false; // 是否压缩图片，默认开启
            this.maxImageSize = options.maxImageSize || 1600; // 最大图片尺寸
            this.imageQuality = options.imageQuality || 0.7; // 图片压缩质量
            this.maxFileSizeBeforeCompress = options.maxFileSizeBeforeCompress || 5 * 1024 * 1024; // 超过5MB才压缩
            this.largeImageQuality = options.largeImageQuality || 0.5; // 大图片压缩质量更低
            this.largeImageThreshold = options.largeImageThreshold || 20 * 1024 * 1024; // 超过20MB的图片使用更低的压缩质量
            this.cancelRequested = false; // 是否请求取消上传
        }

        // 添加文件到上传队列
        addFiles(fileList) {
            // 将FileList对象转换为数组
            this.files = Array.from(fileList);
            this.totalFiles = this.files.length;
            this.currentIndex = 0;
            this.uploadedFiles = 0;
            this.cancelRequested = false;

            // 更新初始进度
            this.updateProgress(0, this.totalFiles);
            
            return this;
        }

        // 开始上传
        start() {
            if (this.files.length === 0) {
                console.warn('No files to upload');
                return;
            }

            this.uploadNext();
        }

        // 上传下一个文件
        uploadNext() {
            if (this.cancelRequested) {
                console.log('Upload cancelled');
                return;
            }

            if (this.currentIndex >= this.files.length) {
                console.log('All files uploaded');
                this.onComplete({
                    success: true,
                    uploadedFiles: this.uploadedFiles,
                    totalFiles: this.totalFiles
                });
                return;
            }

            const file = this.files[this.currentIndex];
            
            // 检查文件类型
            if (this.compressImages && this.isImage(file)) {
                // 如果是图片且启用了压缩，先压缩
                this.compressImage(file)
                    .then(compressedFile => {
                        console.log(`图片压缩: ${file.name} - 原始大小: ${this.formatFileSize(file.size)}, 压缩后: ${this.formatFileSize(compressedFile.size)}`);
                        this.uploadFile(compressedFile, 0);
                    })
                    .catch(error => {
                        console.error('压缩图片失败:', error);
                        // 压缩失败则使用原文件
                        this.uploadFile(file, 0);
                    });
            } else {
                // 不是图片或未启用压缩，直接上传
                this.uploadFile(file, 0);
            }
        }

        // 检查文件是否为图片
        isImage(file) {
            return file.type.startsWith('image/');
        }

        // 压缩图片
        compressImage(file) {
            return new Promise((resolve, reject) => {
                // 如果文件不是图片或小于设定阈值，不压缩
                if (!this.isImage(file) || file.size < this.maxFileSizeBeforeCompress) {
                    resolve(file);
                    return;
                }

                // 确定压缩质量 - 根据文件大小调整
                let quality = this.imageQuality;
                if (file.size > this.largeImageThreshold) {
                    quality = this.largeImageQuality; // 对大图片使用更低的质量
                    console.log(`使用较低压缩质量 ${quality} 处理大文件: ${file.name} (${this.formatFileSize(file.size)})`);
                }

                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = (event) => {
                    const img = new Image();
                    img.src = event.target.result;
                    
                    img.onload = () => {
                        // 计算新尺寸，保持宽高比
                        let { width, height } = img;
                        const maxSize = file.size > this.largeImageThreshold ? 
                                        this.maxImageSize * 0.75 : // 大图片降低25%的尺寸
                                        this.maxImageSize;
                                        
                        if (width > maxSize || height > maxSize) {
                            if (width > height) {
                                height = Math.round(height * (maxSize / width));
                                width = maxSize;
                            } else {
                                width = Math.round(width * (maxSize / height));
                                height = maxSize;
                            }
                        }

                        // 创建Canvas
                        const canvas = document.createElement('canvas');
                        canvas.width = width;
                        canvas.height = height;
                        
                        // 绘制调整后的图像
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, width, height);
                        
                        // 转换为Blob
                        canvas.toBlob(
                            (blob) => {
                                if (!blob) {
                                    reject(new Error('Canvas转换为Blob失败'));
                                    return;
                                }
                                
                                // 创建一个新的File对象
                                const compressedFile = new File(
                                    [blob], 
                                    file.name, 
                                    { type: file.type, lastModified: file.lastModified }
                                );
                                
                                // 如果压缩后文件仍然很大，尝试二次压缩
                                if (compressedFile.size > this.largeImageThreshold && quality > 0.3) {
                                    console.log(`文件仍然过大，尝试二次压缩: ${this.formatFileSize(compressedFile.size)}`);
                                    // 递归调用，但使用更低的质量
                                    this.imageQuality = Math.max(0.3, quality - 0.2);
                                    this.compressImage(compressedFile)
                                        .then(resolve)
                                        .catch(reject);
                                    // 恢复原始质量设置
                                    this.imageQuality = quality;
                                    return;
                                }
                                
                                resolve(compressedFile);
                            }, 
                            file.type, 
                            quality
                        );
                    };
                    
                    img.onerror = () => {
                        reject(new Error('加载图片失败'));
                    };
                };
                
                reader.onerror = () => {
                    reject(new Error('读取文件失败'));
                };
            });
        }

        // 格式化文件大小
        formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        // 上传单个文件
        uploadFile(file, retryCount) {
            if (this.cancelRequested) {
                this.currentIndex++;
                setTimeout(() => this.uploadNext(), 0);
                return;
            }

            const formData = new FormData();
            formData.append('files[]', file); // 使用与后端匹配的名称

            const xhr = new XMLHttpRequest();
            
            // 监听上传进度
            xhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    const fileProgress = event.loaded / event.total;
                    // 单个文件的进度 + 已上传文件的进度
                    const totalProgress = (fileProgress + this.uploadedFiles) / this.totalFiles;
                    this.updateProgress(totalProgress, this.totalFiles, file.name);
                }
            });

            // 请求完成后的处理
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    // 上传成功
                    this.uploadedFiles++;
                    this.currentIndex++;
                    this.updateProgress(this.uploadedFiles / this.totalFiles, this.totalFiles);
                    setTimeout(() => this.uploadNext(), 100); // 短暂延迟，防止服务器过载
                } else {
                    // 上传失败但可重试
                    if (retryCount < this.maxRetries) {
                        console.warn(`上传文件 ${file.name} 失败，正在重试 (${retryCount + 1}/${this.maxRetries})...`);
                        setTimeout(() => this.uploadFile(file, retryCount + 1), 1000);
                    } else {
                        // 超过重试次数，上传下一个文件
                        console.error(`上传文件 ${file.name} 失败，已跳过`);
                        this.onError({
                            file: file,
                            status: xhr.status,
                            response: xhr.responseText
                        });
                        this.currentIndex++;
                        setTimeout(() => this.uploadNext(), 100);
                    }
                }
            });

            // 处理网络错误
            xhr.addEventListener('error', () => {
                if (retryCount < this.maxRetries) {
                    console.warn(`上传文件 ${file.name} 失败，正在重试 (${retryCount + 1}/${this.maxRetries})...`);
                    setTimeout(() => this.uploadFile(file, retryCount + 1), 1000);
                } else {
                    console.error(`上传文件 ${file.name} 失败，已跳过`);
                    this.onError({
                        file: file,
                        status: 'network_error',
                        response: '网络错误'
                    });
                    this.currentIndex++;
                    setTimeout(() => this.uploadNext(), 100);
                }
            });

            // 设置请求头以指示这是AJAX请求
            xhr.open('POST', this.uploadUrl, true);
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            
            // 添加CSRF令牌（如果需要）
            if (this.csrfToken) {
                xhr.setRequestHeader('X-CSRFToken', this.csrfToken);
                // 对于Flask-WTF的CSRF保护，还需要添加表单字段
                formData.append('csrf_token', this.csrfToken);
            }
            
            xhr.send(formData);
        }

        // 更新进度
        updateProgress(progress, total, currentFileName) {
            this.onProgress({
                progress: progress,
                percentage: Math.round(progress * 100),
                uploaded: this.uploadedFiles,
                total: total,
                currentFile: currentFileName || ''
            });
        }

        // 取消上传
        cancel() {
            this.cancelRequested = true;
            console.log('Upload cancelled');
        }
    };
    
    console.log('BatchUploader类已加载');
} else {
    console.log('BatchUploader类已存在，跳过定义');
} 