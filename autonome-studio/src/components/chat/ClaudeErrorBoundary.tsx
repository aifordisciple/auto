'use client';

import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ClaudeErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleBackToNormal = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-gray-900 text-gray-300 p-8">
          <div className="text-red-400 text-lg mb-4">
            Claude 模式加载失败
          </div>
          <div className="text-gray-500 text-sm mb-6 max-w-md text-center">
            {this.state.error?.message || '发生未知错误，请稍后重试。'}
          </div>
          <div className="flex gap-3">
            <button
              onClick={this.handleRetry}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm"
            >
              重试
            </button>
            <button
              onClick={this.handleBackToNormal}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-sm"
            >
              返回常规模式
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
