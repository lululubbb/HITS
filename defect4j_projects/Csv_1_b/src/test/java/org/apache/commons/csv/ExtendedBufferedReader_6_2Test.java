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

class ExtendedBufferedReader_6_2Test {

    ExtendedBufferedReader reader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        reader = new ExtendedBufferedReader(mockReader) {
            // Override read() to call mockReader.read()
            @Override
            public int read() throws IOException {
                return mockReader.read();
            }

            // Override read(char[] buf, int offset, int length) to call mockReader.read()
            @Override
            public int read(char[] buf, int offset, int length) throws IOException {
                return mockReader.read(buf, offset, length);
            }

            // Override readLine to return null to avoid side effects (not used here)
            @Override
            public String readLine() throws IOException {
                return null;
            }

            // Override mark to delegate to mockReader if needed
            @Override
            public void mark(int readAheadLimit) throws IOException {
                mockReader.mark(readAheadLimit);
            }

            // Override reset to delegate to mockReader if needed
            @Override
            public void reset() throws IOException {
                mockReader.reset();
            }
        };
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsNextCharAndResets() throws Exception {
        // Prepare the mock to return 'A' (65) on read()
        when(mockReader.read()).thenReturn((int) 'A');

        // Use reflection to get lookAhead method
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        int result = (int) lookAheadMethod.invoke(reader);

        // Verify that the returned char is 'A'
        assertEquals('A', result);

        // Verify read() was called once on mockReader
        verify(mockReader, times(1)).read();
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStreamWhenReadReturnsMinusOne() throws Exception {
        when(mockReader.read()).thenReturn(-1);

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        int result = (int) lookAheadMethod.invoke(reader);

        assertEquals(-1, result);

        verify(mockReader, times(1)).read();
    }

    @Test
    @Timeout(8000)
    void testLookAheadMultipleCalls() throws Exception {
        // Return 'B' first call, 'C' second call
        when(mockReader.read()).thenReturn((int) 'B', (int) 'C');

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        int first = (int) lookAheadMethod.invoke(reader);
        int second = (int) lookAheadMethod.invoke(reader);

        assertEquals('B', first);
        assertEquals('C', second);

        verify(mockReader, times(2)).read();
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOException() throws Exception {
        when(mockReader.read()).thenThrow(new IOException("read error"));

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        IOException thrown = assertThrows(IOException.class, () -> {
            try {
                lookAheadMethod.invoke(reader);
            } catch (InvocationTargetException e) {
                // unwrap and rethrow the cause if it's IOException
                Throwable cause = e.getCause();
                if (cause instanceof IOException) {
                    throw (IOException) cause;
                } else {
                    throw e;
                }
            }
        });

        assertEquals("read error", thrown.getMessage());
    }

    @Test
    @Timeout(8000)
    void testLookAheadThrowsIOExceptionUnwrapped() throws Exception {
        when(mockReader.read()).thenThrow(new IOException("read error"));

        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        try {
            lookAheadMethod.invoke(reader);
            fail("Expected IOException");
        } catch (InvocationTargetException e) {
            assertTrue(e.getCause() instanceof IOException);
            assertEquals("read error", e.getCause().getMessage());
        }
    }
}