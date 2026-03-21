package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.BufferedReader;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Method;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExtendedBufferedReader_6_1Test {

    ExtendedBufferedReader reader;
    Reader mockReader;

    @BeforeEach
    void setUp() {
        mockReader = mock(Reader.class);
        reader = new ExtendedBufferedReader(mockReader) {
            @Override
            public int read() throws IOException {
                return mockReader.read();
            }

            @Override
            public void mark(int readAheadLimit) throws IOException {
                mockReader.mark(readAheadLimit);
            }

            @Override
            public void reset() throws IOException {
                mockReader.reset();
            }

            @Override
            public boolean markSupported() {
                return true;
            }
        };
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsNextChar() throws Exception {
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenReturn((int) 'A');
        doNothing().when(mockReader).reset();

        int result = reader.lookAhead();
        assertEquals('A', result);

        verify(mockReader, times(1)).mark(1);
        verify(mockReader, times(1)).read();
        verify(mockReader, times(1)).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadReturnsEndOfStream() throws Exception {
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenReturn(-1);
        doNothing().when(mockReader).reset();

        int result = reader.lookAhead();
        assertEquals(-1, result);

        verify(mockReader, times(1)).mark(1);
        verify(mockReader, times(1)).read();
        verify(mockReader, times(1)).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadMultipleCalls() throws Exception {
        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenReturn((int) 'X').thenReturn((int) 'Y');
        doNothing().when(mockReader).reset();

        int first = reader.lookAhead();
        int second = reader.lookAhead();

        assertEquals('X', first);
        assertEquals('X', second);

        verify(mockReader, times(2)).mark(1);
        verify(mockReader, times(2)).read();
        verify(mockReader, times(2)).reset();
    }

    @Test
    @Timeout(8000)
    void testLookAheadPrivateAccessUsingReflection() throws Exception {
        Method lookAheadMethod = ExtendedBufferedReader.class.getDeclaredMethod("lookAhead");
        lookAheadMethod.setAccessible(true);

        when(mockReader.markSupported()).thenReturn(true);
        doNothing().when(mockReader).mark(1);
        when(mockReader.read()).thenReturn((int) 'Z');
        doNothing().when(mockReader).reset();

        int result = (int) lookAheadMethod.invoke(reader);
        assertEquals('Z', result);

        verify(mockReader, times(1)).mark(1);
        verify(mockReader, times(1)).read();
        verify(mockReader, times(1)).reset();
    }

}