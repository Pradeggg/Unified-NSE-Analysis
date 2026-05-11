import AVFoundation
import Foundation

if CommandLine.arguments.count < 3 {
    fputs("usage: record_macos_microphone.swift <output.wav> <seconds>\n", stderr)
    exit(64)
}

let outputPath = CommandLine.arguments[1]
let seconds = Double(CommandLine.arguments[2]) ?? 20.0
let outputURL = URL(fileURLWithPath: outputPath)
try? FileManager.default.createDirectory(
    at: outputURL.deletingLastPathComponent(),
    withIntermediateDirectories: true
)

if #available(macOS 10.14, *) {
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    AVCaptureDevice.requestAccess(for: .audio) { ok in
        granted = ok
        semaphore.signal()
    }
    semaphore.wait()
    if !granted {
        fputs("microphone permission denied for this terminal application\n", stderr)
        exit(77)
    }
}

let settings: [String: Any] = [
    AVFormatIDKey: Int(kAudioFormatLinearPCM),
    AVSampleRateKey: 16000.0,
    AVNumberOfChannelsKey: 1,
    AVLinearPCMBitDepthKey: 16,
    AVLinearPCMIsFloatKey: false,
    AVLinearPCMIsBigEndianKey: false
]

do {
    let recorder = try AVAudioRecorder(url: outputURL, settings: settings)
    recorder.prepareToRecord()
    if !recorder.record() {
        fputs("failed to start microphone recorder\n", stderr)
        exit(70)
    }
    Thread.sleep(forTimeInterval: max(0.25, seconds))
    recorder.stop()
    let attrs = try FileManager.default.attributesOfItem(atPath: outputPath)
    let size = attrs[.size] as? UInt64 ?? 0
    if size <= 44 {
        fputs("recording produced no audio bytes\n", stderr)
        exit(74)
    }
} catch {
    fputs("microphone recording failed: \(error.localizedDescription)\n", stderr)
    exit(70)
}
