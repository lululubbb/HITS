package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_6_3Test {

    ExtendedBufferedReader extendedBufferedReader;
    Reader mockReader;

    @BeforeEach
    void setUp() throws IOException {
        mockReader = mock(Reader.class);
        extendedBufferedReader = new ExtendedBufferedReader(mockReader) {
            // Override read() to delegate to mockReader.read()
            @Override
            public int read() throws IOException {
                return mockReader.read();
            }
            // Override read(char[], int, int) to delegate to mockReader.read(char[], int, int)
            @Override
            public int read(char[] buf, int offset, int length) throws IOException {
                return mockReader.read(buf, offset, length);
            }
            // Override readLine to return null (not used in tests)
            @Override
            public String readLine() throws IOException {
                return null;
            }
            // Override mark to delegate to mockReader if supported
            @Override
            public void mark(int readAheadLimit) throws IOException {
                if (mockReader.markSupported()) {
                    mockReader.mark(readAheadLimit);
                } else {
                    super.mark(readAheadLimit);
                }
            }
            // Override reset to delegate to mockReader if supported
            @Override
            public void reset() throws IOException {
                if (mockReader.markSupported()) {
                    mockReader.reset();
                } else {
                    super.reset();
                }
            }
            // Override markSupported to delegate to mockReader
            @Override
            public boolean markSupported() {
                return mockReader.markSupported();
            }
        };
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsChar() throws Exception {
        // Arrange
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(anyInt());
        when(mockReader.read()).thenReturn((int) 'A');
        doNothing().when(mockReader).reset();

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        // Act
        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);

        // Assert
        assertEquals('A', result);
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStream() throws Exception {
        // Arrange
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(anyInt());
        when(mockReader.read()).thenReturn(-1);
        doNothing().when(mockReader).reset();

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        // Act
        int result = (int) lookAheadMethod.invoke(extendedBufferedReader);

        // Assert
        assertEquals(-1, result);
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOException() throws Exception {
        // Arrange
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(anyInt());
        when(mockReader.read()).thenThrow(new IOException("Read error"));
        doNothing().when(mockReader).reset();

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        // Act & Assert
        InvocationTargetException thrown = assertThrows(InvocationTargetException.class, () -> {
            lookAheadMethod.invoke(extendedBufferedReader);
        });
        assertTrue(thrown.getCause() instanceof IOException);
    }
}